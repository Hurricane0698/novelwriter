//! zh candidate counting: jieba tokenization over batched chapter text plus
//! deterministic recovery of split person names and bound transliteration
//! fragments.

use jieba_rs::Jieba;
use regex::{Match, Matches, Regex};
use rustc_hash::{FxHashMap, FxHashSet};
use std::borrow::Cow;
use std::sync::{LazyLock, Mutex, OnceLock};

use super::lexicon::{
    has_min_chars, is_cjk_token, is_zh_compound_surname, is_zh_name_suffix_title,
    is_zh_name_trailing_block_char, is_zh_single_surname, looks_like_zh_translit_fragment,
    prefix_chars, strip_zh_person_name_trailing_noise, ZH_FRAGMENT_MAX_TOKEN_CHARS,
};
use super::normalize::{
    classify_match_normalization, normalize_for_matching, normalize_token, MatchNormalization,
};
use super::CandidateCount;

const ZH_SPLIT_NAME_MIN_COUNT: CandidateCount = 2;
const ZH_FRAGMENT_EXTENSION_MIN_COUNT: CandidateCount = 3;
const ZH_FRAGMENT_DOMINANCE_THRESHOLD: f32 = 0.85;

static ZH_TOKENIZER: OnceLock<Mutex<Option<Jieba>>> = OnceLock::new();

static COUNT_RE_HAN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"([\u{3400}-\u{4DBF}\u{4E00}-\u{9FFF}\u{F900}-\u{FAFF}\u{20000}-\u{2A6DF}\u{2A700}-\u{2B73F}\u{2B740}-\u{2B81F}\u{2B820}-\u{2CEAF}\u{2CEB0}-\u{2EBEF}\u{2F800}-\u{2FA1F}a-zA-Z0-9+#&\._%\-]+)"
    ).expect("han block regex")
});
static COUNT_RE_SKIP: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(\r\n|\s)").expect("skip regex"));

fn zh_tokenizer_state() -> &'static Mutex<Option<Jieba>> {
    ZH_TOKENIZER.get_or_init(|| Mutex::new(None))
}

pub(crate) fn with_zh_tokenizer<R>(f: impl FnOnce(&Jieba) -> R) -> R {
    let mut tokenizer = zh_tokenizer_state()
        .lock()
        .expect("zh tokenizer mutex poisoned");
    let tokenizer = tokenizer.get_or_insert_with(Jieba::new);
    f(tokenizer)
}

/// Drop the cached jieba dictionary so idle workers do not pin its memory.
pub(crate) fn release_zh_tokenizer() {
    let mut tokenizer = zh_tokenizer_state()
        .lock()
        .expect("zh tokenizer mutex poisoned");
    tokenizer.take();
}

struct SplitMatches<'r, 't> {
    finder: Matches<'r, 't>,
    text: &'t str,
    last: usize,
    matched: Option<Match<'t>>,
}

impl<'r, 't> SplitMatches<'r, 't> {
    #[inline]
    fn new(re: &'r Regex, text: &'t str) -> SplitMatches<'r, 't> {
        SplitMatches {
            finder: re.find_iter(text),
            text,
            last: 0,
            matched: None,
        }
    }
}

enum SplitState<'t> {
    Unmatched(&'t str),
    Matched(Match<'t>),
}

impl<'t> SplitState<'t> {
    #[inline]
    fn as_str(&self) -> &'t str {
        match self {
            SplitState::Unmatched(text) => text,
            SplitState::Matched(matched) => matched.as_str(),
        }
    }

    #[inline]
    fn is_matched(&self) -> bool {
        matches!(self, SplitState::Matched(_))
    }
}

impl<'r, 't> Iterator for SplitMatches<'r, 't> {
    type Item = SplitState<'t>;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        if let Some(matched) = self.matched.take() {
            self.last = matched.end();
            return Some(SplitState::Matched(matched));
        }

        if let Some(matched) = self.finder.next() {
            if matched.start() != self.last {
                let unmatched = &self.text[self.last..matched.start()];
                self.matched = Some(matched);
                self.last = matched.start();
                return Some(SplitState::Unmatched(unmatched));
            }
            self.last = matched.end();
            return Some(SplitState::Matched(matched));
        }

        if self.last != self.text.len() {
            let unmatched = &self.text[self.last..];
            self.last = self.text.len();
            return Some(SplitState::Unmatched(unmatched));
        }

        None
    }
}

/// Accumulates raw token counts plus the side-channels used to recover
/// candidates that jieba splits apart (person names, translit fragments).
#[derive(Default)]
struct ZhCandidateCounts {
    candidates: FxHashMap<String, CandidateCount>,
    recovered_names: FxHashMap<String, CandidateCount>,
    fragment_pairs: FxHashMap<(String, String), CandidateCount>,
    fragment_outgoing: FxHashMap<String, CandidateCount>,
    fragment_incoming: FxHashMap<String, CandidateCount>,
}

impl ZhCandidateCounts {
    fn flush_batch(&mut self, batch_text: &mut String, common_words: &FxHashSet<String>) {
        if batch_text.is_empty() {
            return;
        }
        self.count_batch(batch_text.as_str(), common_words);
        batch_text.clear();
    }

    fn count_batch(&mut self, text: &str, common_words: &FxHashSet<String>) {
        let mut batch_counts: FxHashMap<Cow<'_, str>, CandidateCount> = FxHashMap::default();
        let mut tokenizer = None::<std::sync::MutexGuard<'_, Option<Jieba>>>;
        for state in SplitMatches::new(&COUNT_RE_HAN, text) {
            match state {
                SplitState::Matched(matched) => {
                    let block = matched.as_str();
                    if is_simple_ascii_alnum_block(block) {
                        count_candidate_token(block, common_words, &mut batch_counts);
                        continue;
                    }
                    let tokenizer = tokenizer
                        .get_or_insert_with(|| {
                            zh_tokenizer_state()
                                .lock()
                                .expect("zh tokenizer mutex poisoned")
                        })
                        .get_or_insert_with(Jieba::new);
                    let mut previous_cjk_token = None::<String>;
                    let mut previous_fragment_token = None::<String>;
                    for token in tokenizer.cut(block, true) {
                        let normalized = normalize_token(token);
                        count_candidate_token_normalized(
                            normalized.clone(),
                            common_words,
                            &mut batch_counts,
                        );
                        if let Some(left) = previous_cjk_token.as_deref() {
                            if let Some(candidate) =
                                merge_split_zh_name_tokens(left, normalized.as_ref())
                            {
                                if !common_words.contains(candidate.as_str()) {
                                    increment_candidate_count(&mut self.recovered_names, candidate);
                                }
                            }
                        }
                        if is_zh_fragment_token(normalized.as_ref(), common_words) {
                            if let Some(left) = previous_fragment_token.as_deref() {
                                self.count_fragment_pair(left, normalized.as_ref());
                            }
                            previous_fragment_token = Some(normalized.to_string());
                        } else {
                            previous_fragment_token = None;
                        }
                        if is_cjk_token(normalized.as_ref()) {
                            previous_cjk_token = Some(normalized.into_owned());
                        } else {
                            previous_cjk_token = None;
                        }
                    }
                }
                SplitState::Unmatched(unmatched) => {
                    for skip_state in SplitMatches::new(&COUNT_RE_SKIP, unmatched) {
                        let word = skip_state.as_str();
                        if word.is_empty() || skip_state.is_matched() {
                            continue;
                        }
                        let mut word_indices = word.char_indices().map(|(idx, _)| idx).peekable();
                        while let Some(byte_start) = word_indices.next() {
                            let token = if let Some(byte_end) = word_indices.peek() {
                                &word[byte_start..*byte_end]
                            } else {
                                &word[byte_start..]
                            };
                            count_candidate_token(token, common_words, &mut batch_counts);
                        }
                    }
                }
            }
        }
        for (candidate, count) in batch_counts {
            if let Some(existing) = self.candidates.get_mut(candidate.as_ref()) {
                *existing = existing
                    .checked_add(count)
                    .expect("candidate count overflow");
            } else {
                self.candidates.insert(candidate.into_owned(), count);
            }
        }
    }

    fn count_fragment_pair(&mut self, left: &str, right: &str) {
        increment_candidate_count(
            &mut self.fragment_pairs,
            (left.to_owned(), right.to_owned()),
        );
        increment_candidate_count(&mut self.fragment_outgoing, left.to_owned());
        increment_candidate_count(&mut self.fragment_incoming, right.to_owned());
    }

    fn finalize(self, common_words: &FxHashSet<String>) -> FxHashMap<String, CandidateCount> {
        let ZhCandidateCounts {
            mut candidates,
            recovered_names,
            fragment_pairs,
            fragment_outgoing,
            fragment_incoming,
        } = self;
        merge_recovered_zh_name_counts(&mut candidates, recovered_names);
        recover_bound_zh_fragment_candidates(
            &mut candidates,
            common_words,
            fragment_pairs,
            fragment_outgoing,
            fragment_incoming,
        );
        merge_zh_person_name_shadow_counts(&mut candidates);
        candidates
    }
}

/// Count zh candidate tokens over `chapters`, concatenating small chapters
/// into batches of at most `max_batch_chars` bytes per jieba pass.
pub(crate) fn collect_candidate_counts<T>(
    chapters: T,
    common_word_set: &FxHashSet<String>,
    max_batch_chars: usize,
) -> Vec<(String, usize)>
where
    T: IntoIterator,
    T::Item: AsRef<str>,
{
    let mut counts = ZhCandidateCounts::default();
    let batch_limit = max_batch_chars.max(1);
    let mut batch_text = String::new();

    for chapter in chapters {
        let chapter: &str = chapter.as_ref();
        if chapter.is_empty() {
            continue;
        }
        if chapter.len() >= batch_limit {
            counts.flush_batch(&mut batch_text, common_word_set);
            counts.count_batch(chapter, common_word_set);
            continue;
        }

        if !batch_text.is_empty() && batch_text.len() + 2 + chapter.len() > batch_limit {
            counts.flush_batch(&mut batch_text, common_word_set);
        }
        if !batch_text.is_empty() {
            batch_text.push('\n');
            batch_text.push('\n');
        }
        batch_text.push_str(chapter);
    }
    counts.flush_batch(&mut batch_text, common_word_set);

    counts
        .finalize(common_word_set)
        .into_iter()
        .map(|(name, count)| (name, count as usize))
        .collect()
}

fn merge_zh_person_name_shadow_counts(candidate_counts: &mut FxHashMap<String, CandidateCount>) {
    if candidate_counts.is_empty() {
        return;
    }

    let shadow_entries: Vec<(String, String, CandidateCount)> = candidate_counts
        .iter()
        .filter_map(|(candidate, count)| {
            let canonical = strip_zh_person_name_trailing_noise(candidate)?;
            candidate_counts.contains_key(canonical).then_some((
                candidate.clone(),
                canonical.to_owned(),
                *count,
            ))
        })
        .collect();

    for (shadow, canonical, count) in shadow_entries {
        if shadow == canonical || count == 0 {
            continue;
        }
        if candidate_counts.remove(&shadow).is_none() {
            continue;
        }
        *candidate_counts.entry(canonical).or_insert(0) += count;
    }
}

pub(crate) fn candidate_count_cmp(
    left: &(String, usize),
    right: &(String, usize),
) -> std::cmp::Ordering {
    right
        .1
        .cmp(&left.1)
        .then_with(|| right.0.chars().count().cmp(&left.0.chars().count()))
        .then_with(|| left.0.cmp(&right.0))
}

pub(crate) fn sort_candidate_counts(items: &mut [(String, usize)]) {
    items.sort_unstable_by(candidate_count_cmp);
}

pub(crate) fn truncate_candidate_counts_topk(items: &mut Vec<(String, usize)>, limit: usize) {
    if limit == 0 {
        items.clear();
        return;
    }
    if items.len() <= limit {
        return;
    }

    let split_index = limit - 1;
    items.select_nth_unstable_by(split_index, candidate_count_cmp);
    items.truncate(limit);
    sort_candidate_counts(items);
}

fn merge_recovered_zh_name_counts(
    candidate_counts: &mut FxHashMap<String, CandidateCount>,
    recovered_name_counts: FxHashMap<String, CandidateCount>,
) {
    for (candidate, count) in recovered_name_counts {
        if count < ZH_SPLIT_NAME_MIN_COUNT {
            continue;
        }
        match candidate_counts.entry(candidate) {
            std::collections::hash_map::Entry::Occupied(mut entry) => {
                if *entry.get() < count {
                    *entry.get_mut() = count;
                }
            }
            std::collections::hash_map::Entry::Vacant(entry) => {
                entry.insert(count);
            }
        }
    }
}

fn is_simple_ascii_alnum_block(value: &str) -> bool {
    !value.is_empty() && value.chars().all(|ch| ch.is_ascii_alphanumeric())
}

fn count_candidate_token<'a>(
    token: &'a str,
    common_words: &FxHashSet<String>,
    batch_counts: &mut FxHashMap<Cow<'a, str>, CandidateCount>,
) {
    let normalized = normalize_token(token);
    count_candidate_token_normalized(normalized, common_words, batch_counts);
}

fn count_candidate_token_normalized<'a>(
    normalized: Cow<'a, str>,
    common_words: &FxHashSet<String>,
    batch_counts: &mut FxHashMap<Cow<'a, str>, CandidateCount>,
) {
    let normalized_ref = normalized.as_ref();
    if !has_min_chars(normalized_ref, 2) {
        return;
    }
    if common_words.contains(normalized_ref) {
        return;
    }
    match classify_match_normalization(normalized_ref) {
        MatchNormalization::None => {}
        MatchNormalization::AsciiLower => {
            let match_candidate = normalized_ref.to_ascii_lowercase();
            if common_words.contains(match_candidate.as_str()) {
                return;
            }
        }
        MatchNormalization::UnicodeCaseFold => {
            let match_candidate = normalize_for_matching(normalized_ref);
            if match_candidate.as_ref() != normalized_ref
                && common_words.contains(match_candidate.as_ref())
            {
                return;
            }
        }
    }
    if let Some(count) = batch_counts.get_mut(normalized_ref) {
        *count = count
            .checked_add(1)
            .expect("batch candidate count overflow");
    } else {
        batch_counts.insert(normalized, 1);
    }
}

fn is_zh_fragment_token(token: &str, common_words: &FxHashSet<String>) -> bool {
    !token.is_empty()
        && token.chars().count() <= ZH_FRAGMENT_MAX_TOKEN_CHARS
        && is_cjk_token(token)
        && !common_words.contains(token)
        && (looks_like_zh_translit_fragment(token) || is_zh_name_suffix_title(token))
}

fn increment_candidate_count<K>(counts: &mut FxHashMap<K, CandidateCount>, key: K)
where
    K: std::hash::Hash + Eq,
{
    if let Some(existing) = counts.get_mut(&key) {
        *existing = existing.checked_add(1).expect("candidate count overflow");
    } else {
        counts.insert(key, 1);
    }
}

/// Merge dominant adjacent fragment chains ("拉蒂"+"莉娅") back into full
/// candidates, discounting the fragments they were recovered from.
fn recover_bound_zh_fragment_candidates(
    candidate_counts: &mut FxHashMap<String, CandidateCount>,
    common_words: &FxHashSet<String>,
    pair_counts: FxHashMap<(String, String), CandidateCount>,
    outgoing_counts: FxHashMap<String, CandidateCount>,
    incoming_counts: FxHashMap<String, CandidateCount>,
) {
    if pair_counts.is_empty() {
        return;
    }

    let mut best_successor: FxHashMap<String, (String, CandidateCount)> = FxHashMap::default();
    let mut best_predecessor: FxHashMap<String, (String, CandidateCount)> = FxHashMap::default();
    let mut ambiguous_successors: FxHashSet<String> = FxHashSet::default();
    let mut ambiguous_predecessors: FxHashSet<String> = FxHashSet::default();

    for ((left, right), count) in pair_counts {
        if count < ZH_FRAGMENT_EXTENSION_MIN_COUNT {
            continue;
        }
        let outgoing = outgoing_counts.get(left.as_str()).copied().unwrap_or(0);
        let incoming = incoming_counts.get(right.as_str()).copied().unwrap_or(0);
        if outgoing == 0 || incoming == 0 {
            continue;
        }
        if (count as f32 / outgoing as f32) < ZH_FRAGMENT_DOMINANCE_THRESHOLD
            || (count as f32 / incoming as f32) < ZH_FRAGMENT_DOMINANCE_THRESHOLD
        {
            continue;
        }

        match best_successor.get(left.as_str()) {
            Some((_, best_count)) if *best_count > count => {}
            Some((best_right, best_count)) if *best_count == count && best_right != &right => {
                ambiguous_successors.insert(left.clone());
            }
            _ => {
                best_successor.insert(left.clone(), (right.clone(), count));
                ambiguous_successors.remove(left.as_str());
            }
        }

        match best_predecessor.get(right.as_str()) {
            Some((_, best_count)) if *best_count > count => {}
            Some((best_left, best_count)) if *best_count == count && best_left != &left => {
                ambiguous_predecessors.insert(right.clone());
            }
            _ => {
                best_predecessor.insert(right.clone(), (left.clone(), count));
                ambiguous_predecessors.remove(right.as_str());
            }
        }
    }

    let start_tokens: Vec<String> = best_successor
        .keys()
        .filter(|left| {
            !ambiguous_successors.contains(left.as_str())
                && !best_predecessor.contains_key(left.as_str())
                && looks_like_zh_translit_fragment(left.as_str())
        })
        .cloned()
        .collect();

    for start in start_tokens {
        let mut fragments = vec![start.clone()];
        let mut chain_count = CandidateCount::MAX;
        let mut current = start;
        let mut seen: FxHashSet<String> = FxHashSet::default();
        seen.insert(current.clone());

        while !ambiguous_successors.contains(current.as_str()) {
            if is_zh_name_suffix_title(current.as_str()) {
                break;
            }
            let Some((next_token, edge_count)) = best_successor.get(current.as_str()) else {
                break;
            };
            let next_token = next_token.clone();
            if seen.contains(next_token.as_str())
                || ambiguous_predecessors.contains(next_token.as_str())
            {
                break;
            }
            let Some((predecessor, _)) = best_predecessor.get(next_token.as_str()) else {
                break;
            };
            if predecessor != &current {
                break;
            }

            fragments.push(next_token.clone());
            chain_count = chain_count.min(*edge_count);
            seen.insert(next_token.clone());
            current = next_token;
            if is_zh_name_suffix_title(current.as_str()) {
                break;
            }
        }

        if fragments.len() < 2 {
            continue;
        }

        let merged = fragments.concat();
        if merged.chars().count() < 3
            || merged.chars().collect::<FxHashSet<char>>().len() < 2
            || common_words.contains(merged.as_str())
        {
            continue;
        }

        match candidate_counts.get_mut(merged.as_str()) {
            Some(existing) => {
                if *existing < chain_count {
                    *existing = chain_count;
                }
            }
            None => {
                candidate_counts.insert(merged, chain_count);
            }
        }
        for fragment in fragments {
            let should_remove = if let Some(existing) = candidate_counts.get_mut(fragment.as_str())
            {
                *existing = existing.saturating_sub(chain_count);
                *existing == 0
            } else {
                false
            };
            if should_remove {
                candidate_counts.remove(fragment.as_str());
            }
        }
    }
}

/// Recombine person names that jieba split across token boundaries, e.g.
/// compound surname + given name.
fn merge_split_zh_name_tokens(left: &str, right: &str) -> Option<String> {
    if !is_cjk_token(left) || !is_cjk_token(right) {
        return None;
    }

    let left_len = left.chars().count();
    let right_len = right.chars().count();
    if right_len == 1
        && right
            .chars()
            .next()
            .is_some_and(is_zh_name_trailing_block_char)
    {
        return None;
    }

    if left_len == 2 && is_zh_compound_surname(left) && matches!(right_len, 1 | 2) {
        return Some(format!("{left}{right}"));
    }
    if left_len == 3 && prefix_chars(left, 2).is_some_and(is_zh_compound_surname) && right_len == 1
    {
        return Some(format!("{left}{right}"));
    }
    if left_len == 1 && is_zh_single_surname(left) && right_len == 2 {
        return Some(format!("{left}{right}"));
    }
    if left_len == 2 && prefix_chars(left, 1).is_some_and(is_zh_single_surname) && right_len == 1 {
        return Some(format!("{left}{right}"));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merge_split_zh_name_tokens_recovers_names_and_blocks_noise() {
        assert_eq!(
            merge_split_zh_name_tokens("慕容雪", "晴").as_deref(),
            Some("慕容雪晴")
        );
        assert_eq!(
            merge_split_zh_name_tokens("欧阳", "明月").as_deref(),
            Some("欧阳明月")
        );
        assert_eq!(
            merge_split_zh_name_tokens("顾慎", "为").as_deref(),
            Some("顾慎为")
        );
        assert_eq!(merge_split_zh_name_tokens("张纲", "一"), None);
        assert_eq!(merge_split_zh_name_tokens("张钢", "走"), None);
    }

    #[test]
    fn merge_zh_person_name_shadow_counts_merges_only_safe_variants() {
        let mut candidate_counts: FxHashMap<String, CandidateCount> = FxHashMap::default();
        candidate_counts.insert("罗碧".to_owned(), 10);
        candidate_counts.insert("罗碧不".to_owned(), 3);
        candidate_counts.insert("罗碧看".to_owned(), 2);
        candidate_counts.insert("炙皇星看".to_owned(), 4);

        merge_zh_person_name_shadow_counts(&mut candidate_counts);

        assert_eq!(candidate_counts.get("罗碧"), Some(&15));
        assert_eq!(candidate_counts.get("罗碧不"), None);
        assert_eq!(candidate_counts.get("罗碧看"), None);
        assert_eq!(candidate_counts.get("炙皇星看"), Some(&4));
    }

    #[test]
    fn sort_candidate_counts_prefers_longer_names_when_counts_tie() {
        let mut items = vec![
            ("慕容雪".to_owned(), 3usize),
            ("慕容雪晴".to_owned(), 3usize),
            ("顾慎".to_owned(), 2usize),
            ("顾慎为".to_owned(), 2usize),
        ];

        sort_candidate_counts(&mut items);

        assert_eq!(items[0].0, "慕容雪晴");
        assert_eq!(items[1].0, "慕容雪");
        assert_eq!(items[2].0, "顾慎为");
        assert_eq!(items[3].0, "顾慎");
    }

    #[test]
    fn count_batches_recover_split_person_names() {
        let mut counts = ZhCandidateCounts::default();
        let common_words = FxHashSet::default();

        counts.count_batch(
            "慕容雪晴来到大厅。慕容雪晴看着欧阳明月，欧阳明月也看着慕容雪晴。顾慎为与荷女对视。顾慎为没有说话。",
            &common_words,
        );
        let candidate_counts = counts.finalize(&common_words);

        assert_eq!(candidate_counts.get("慕容雪晴"), Some(&3));
        assert_eq!(candidate_counts.get("欧阳明月"), Some(&2));
        assert_eq!(candidate_counts.get("顾慎为"), Some(&2));
    }

    #[test]
    fn count_batches_recover_bound_fragment_names_and_discount_fragments() {
        let mut counts = ZhCandidateCounts::default();
        let common_words = FxHashSet::default();

        counts.count_batch(
            "拉蒂莉娅看见坎贝斯莉太太。拉蒂莉娅向坎贝斯莉太太行礼。拉蒂莉娅又遇见坎贝斯莉太太。",
            &common_words,
        );
        let candidate_counts = counts.finalize(&common_words);

        assert_eq!(candidate_counts.get("拉蒂莉娅"), Some(&3));
        assert_eq!(candidate_counts.get("坎贝斯莉太太"), Some(&3));
        assert_eq!(candidate_counts.get("拉蒂"), None);
        assert_eq!(candidate_counts.get("贝斯"), None);
        assert_eq!(candidate_counts.get("太太"), None);
    }
}
