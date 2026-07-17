//! Block-level zh candidate refinement: seed surfaces from fast counts, scan
//! narrative blocks with local span extension, score boundary entropy, then
//! collapse surface variants into canonical candidates.

use aho_corasick::AhoCorasick;
use rustc_hash::{FxHashMap, FxHashSet};

use crate::core::{normalize_chapter_text, segment_chapter_text_without_index};

use super::candidates::{
    collect_candidate_counts, release_zh_tokenizer, truncate_candidate_counts_topk,
};
use super::lexicon::{
    all_same_chars, is_cjk_name_char, is_cjk_token, is_short_translit_fragment,
    is_zh_compound_surname, is_zh_name_suffix_title, is_zh_name_trailing_block_char,
    is_zh_single_surname_char, looks_like_zh_person_name, prefix_chars,
    strip_zh_person_name_trailing_noise, suffix_after_removing_prefix_chars,
};
use super::{collect_char_starts_into, CandidateCount};

const ZH_BLOCK_MIN_OCCURRENCES: usize = 3;
const ZH_BLOCK_MIN_BLOCKS: usize = 1;
const ZH_BLOCK_DISCOVERY_MULTIPLIER: usize = 8;
const ZH_BLOCK_DISCOVERY_HARD_CAP: usize = 2048;
const ZH_BLOCK_RETURN_MULTIPLIER: usize = 6;
const ZH_BLOCK_RETURN_HARD_CAP: usize = 768;
const ZH_BLOCK_MIN_BOUNDARY_ENTROPY: f64 = 0.55;
const ZH_BLOCK_MIN_EXTENSION_CONTAINMENT: f64 = 0.90;
const ZH_BLOCK_MIN_EXTENSION_SCORE_MARGIN: f64 = 0.75;
const ZH_BLOCK_FRAGMENT_DIRECTIONAL_ENTROPY_MAX: f64 = 1.6;
const ZH_BLOCK_FRAGMENT_EXTENSION_MIN_CONTAINMENT: f64 = 0.82;
const ZH_BLOCK_FRAGMENT_EXTENSION_MAX_SECONDARY_RATIO: f64 = 0.5;
const ZH_BLOCK_LOCAL_EXTENSION_MAX_EXTRA_CHARS: usize = 2;
const ZH_BLOCK_GENERIC_MODIFIER_PREFIX_CHARS: &str = "大小老新旧高低前后左右上下内外";
const ZH_BLOCK_LOW_VALUE_PREFIX_CHARS: &str = "一都这那没了着出个自给将把向从对跟比于其各每该本此";
const ZH_BLOCK_LOW_VALUE_SUFFIX_CHARS: &str = "了着过啊呀吧呢吗么的";
const ZH_BLOCK_LOW_VALUE_INTERIOR_CHARS: &str = "的";
const ZH_BLOCK_EXTRA_SINGLE_SURNAMES: &str = "林花贺兰佟柯";
const ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS: &str =
    "了不的来去都也就在上里看说没是有把将和与着出个给这那好太很再更向从对跟比于到等让";
const ZH_BLOCK_TWO_CHAR_HINT_SUFFIXES: &str =
    "星际焰兽师士器盘镯石药炉体子司营府院门宗派盟帮城港谷湖河山殿宫阁楼坊铺";
const ZH_BLOCK_GENERIC_ROLE_SUFFIX_CHARS: &str = "后帝王君皇妃司师使神主尊圣";

/// Compact output of block refinement:
/// `(surface_names, importance items, co-occurrence pairs, canonical -> surfaces)`.
pub(crate) type CompactRefinementOutput = (
    Vec<String>,
    Vec<(usize, usize)>,
    Vec<(usize, usize, usize)>,
    Vec<(usize, Vec<usize>)>,
);

#[derive(Debug, Clone, Default)]
struct BlockSurfaceAccumulator {
    raw_occurrences: usize,
    block_count: usize,
    left_contexts: FxHashMap<BoundarySymbol, CandidateCount>,
    right_contexts: FxHashMap<BoundarySymbol, CandidateCount>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum BoundarySymbol {
    Start,
    End,
    Whitespace,
    Punctuation,
    Char(char),
}

#[derive(Debug, Clone)]
struct RepeatedSpanSurfaceStat {
    surface_id: usize,
    char_len: usize,
    raw_occurrences: usize,
    block_count: usize,
    left_entropy: f64,
    right_entropy: f64,
    discovery_score: f64,
}

#[derive(Debug, Clone)]
struct CanonicalCandidate {
    canonical_id: usize,
    importance: usize,
    block_count: usize,
    discovery_score: f64,
    surface_ids: Vec<usize>,
}

/// Interned surfaces with their per-surface accumulators and block postings.
#[derive(Debug, Default)]
struct SurfaceIndex {
    id_by_name: FxHashMap<String, usize>,
    names: Vec<String>,
    accumulators: Vec<BlockSurfaceAccumulator>,
    blocks: Vec<Vec<usize>>,
}

/// Per-block scan context: block chars, common-word filter, and dedupe state.
#[derive(Debug)]
struct BlockPass<'a> {
    chars: &'a [char],
    common_words: &'a FxHashSet<String>,
    seen_in_block: FxHashSet<usize>,
    seen_occurrences: FxHashSet<(usize, usize, usize)>,
}

impl<'a> BlockPass<'a> {
    fn new(chars: &'a [char], common_words: &'a FxHashSet<String>) -> Self {
        Self {
            chars,
            common_words,
            seen_in_block: FxHashSet::default(),
            seen_occurrences: FxHashSet::default(),
        }
    }
}

impl SurfaceIndex {
    fn get_or_insert(&mut self, surface: &str) -> usize {
        if let Some(&surface_id) = self.id_by_name.get(surface) {
            return surface_id;
        }
        let owned = surface.to_owned();
        let surface_id = self.names.len();
        self.id_by_name.insert(owned.clone(), surface_id);
        self.names.push(owned);
        self.accumulators.push(BlockSurfaceAccumulator::default());
        self.blocks.push(Vec::new());
        surface_id
    }

    fn record_occurrence(
        &mut self,
        pass: &mut BlockPass<'_>,
        surface: &str,
        start_char: usize,
        end_char: usize,
        trust_seed_surface: bool,
    ) {
        if surface.is_empty() {
            return;
        }
        if !trust_seed_surface && is_low_value_surface(surface, pass.common_words) {
            return;
        }

        let surface_id = self.get_or_insert(surface);
        if !pass
            .seen_occurrences
            .insert((surface_id, start_char, end_char))
        {
            return;
        }

        let left_boundary = if start_char == 0 {
            BoundarySymbol::Start
        } else {
            normalize_boundary_symbol(pass.chars[start_char - 1])
        };
        let right_boundary = if end_char >= pass.chars.len() {
            BoundarySymbol::End
        } else {
            normalize_boundary_symbol(pass.chars[end_char])
        };
        let accumulator = &mut self.accumulators[surface_id];
        accumulator.raw_occurrences += 1;
        *accumulator.left_contexts.entry(left_boundary).or_insert(0) += 1;
        *accumulator
            .right_contexts
            .entry(right_boundary)
            .or_insert(0) += 1;
        pass.seen_in_block.insert(surface_id);
    }
}

/// Entry point: refine fast seed counts against narrative blocks and return
/// the compact `(names, importance, pairs, canonical_surfaces)` output.
pub(crate) fn build_block_refinement_inputs(
    normalized_chapters: Vec<String>,
    common_word_set: &FxHashSet<String>,
    limit: usize,
) -> Result<CompactRefinementOutput, String> {
    let discovery_limit = usize::min(
        usize::max(limit.saturating_mul(ZH_BLOCK_DISCOVERY_MULTIPLIER), 1024),
        ZH_BLOCK_DISCOVERY_HARD_CAP,
    );
    let mut seed_candidates = collect_candidate_counts(
        normalized_chapters.iter().map(|chapter| chapter.as_str()),
        common_word_set,
        256 * 1024,
    );
    truncate_candidate_counts_topk(&mut seed_candidates, discovery_limit);
    release_zh_tokenizer();
    if seed_candidates.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new(), Vec::new()));
    }

    let blocks = segment_chapters_into_blocks(&normalized_chapters);
    if blocks.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new(), Vec::new()));
    }

    let effective_min_blocks = if blocks.len() <= 1 {
        1
    } else {
        ZH_BLOCK_MIN_BLOCKS
    };
    let (surface_index, surface_stats, block_present_surfaces) = collect_seeded_surface_stats(
        &blocks,
        common_word_set,
        &seed_candidates,
        ZH_BLOCK_MIN_OCCURRENCES,
        effective_min_blocks,
    )?;
    if surface_stats.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new(), Vec::new()));
    }

    let canonical_candidates =
        build_canonical_candidates(&surface_index.names, &surface_stats, &surface_index.blocks);
    if canonical_candidates.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new(), Vec::new()));
    }

    let return_limit = usize::min(
        usize::max(limit.saturating_mul(ZH_BLOCK_RETURN_MULTIPLIER), 256),
        ZH_BLOCK_RETURN_HARD_CAP,
    );
    let selected_candidates = canonical_candidates
        .into_iter()
        .take(return_limit)
        .collect::<Vec<_>>();
    Ok(compact_selected_candidates_output(
        &surface_index.names,
        &selected_candidates,
        &block_present_surfaces,
    ))
}

fn segment_chapters_into_blocks<T>(chapters: T) -> Vec<String>
where
    T: IntoIterator,
    T::Item: AsRef<str>,
{
    let mut blocks = Vec::new();
    let mut char_starts = Vec::new();

    for (chapter_idx, chapter) in chapters.into_iter().enumerate() {
        let normalized = normalize_chapter_text(chapter.as_ref());
        if normalized.is_empty() {
            continue;
        }
        collect_char_starts_into(&normalized, &mut char_starts);
        let segments = segment_chapter_text_without_index(
            (chapter_idx + 1) as i64,
            (chapter_idx + 1) as i64,
            &normalized,
        );
        for segment in segments {
            let start_char = segment.start_pos.max(0) as usize;
            let end_char = segment.end_pos.max(0) as usize;
            if start_char >= end_char || end_char >= char_starts.len() {
                continue;
            }
            let block_text = normalized[char_starts[start_char]..char_starts[end_char]].trim();
            if block_text.is_empty() {
                continue;
            }
            blocks.push(block_text.to_owned());
        }
    }

    blocks
}

/// Result of the block scan: interned surfaces, score-ordered surface stats,
/// and the per-block list of present surface ids.
type SeededSurfaceStats = (SurfaceIndex, Vec<RepeatedSpanSurfaceStat>, Vec<Vec<usize>>);

fn collect_seeded_surface_stats(
    blocks: &[String],
    common_words: &FxHashSet<String>,
    seed_candidates: &[(String, usize)],
    min_occurrences: usize,
    min_blocks: usize,
) -> Result<SeededSurfaceStats, String> {
    let mut seed_names = seed_candidates
        .iter()
        .filter_map(|(surface, _)| {
            let char_len = surface.chars().count();
            (char_len >= 2 && is_cjk_token(surface.as_str())).then_some(surface.clone())
        })
        .collect::<Vec<_>>();
    seed_names.sort_unstable_by(|left, right| {
        right
            .chars()
            .count()
            .cmp(&left.chars().count())
            .then_with(|| left.cmp(right))
    });
    seed_names.dedup();
    if seed_names.is_empty() {
        return Ok((SurfaceIndex::default(), Vec::new(), Vec::new()));
    }
    let seed_name_set: FxHashSet<String> = seed_names.iter().cloned().collect();

    let automaton = AhoCorasick::new(
        seed_names
            .iter()
            .map(|surface| surface.as_str())
            .collect::<Vec<_>>(),
    )
    .map_err(|err| err.to_string())?;
    let seed_char_lens = seed_names
        .iter()
        .map(|surface| surface.chars().count())
        .collect::<Vec<_>>();
    let mut surface_index = SurfaceIndex::default();
    let mut block_present_surfaces = Vec::new();
    let mut char_starts = Vec::new();

    for (block_idx, block_text) in blocks.iter().enumerate() {
        if block_text.is_empty() {
            continue;
        }
        let chars: Vec<char> = block_text.chars().collect();
        if chars.len() < 2 {
            continue;
        }
        collect_char_starts_into(block_text.as_str(), &mut char_starts);
        let mut pass = BlockPass::new(&chars, common_words);
        let mut char_cursor = 0usize;

        for matched in automaton.find_overlapping_iter(block_text.as_str()) {
            let seed_id = matched.pattern().as_usize();
            let start_byte = matched.start();
            while char_cursor + 1 < char_starts.len() && char_starts[char_cursor + 1] <= start_byte
            {
                char_cursor += 1;
            }
            let start_char = char_cursor;
            let end_char = start_char + seed_char_lens[seed_id];
            if end_char > chars.len() {
                continue;
            }

            surface_index.record_occurrence(
                &mut pass,
                &seed_names[seed_id],
                start_char,
                end_char,
                true,
            );
            record_local_seed_extensions(
                &mut surface_index,
                &mut pass,
                &seed_names[seed_id],
                start_char,
                end_char,
                block_text.as_str(),
                &char_starts,
            );
        }

        if pass.seen_in_block.is_empty() {
            continue;
        }
        let mut present_ids = pass.seen_in_block.into_iter().collect::<Vec<_>>();
        present_ids.sort_unstable();
        for &surface_id in &present_ids {
            surface_index.blocks[surface_id].push(block_idx);
            surface_index.accumulators[surface_id].block_count += 1;
        }
        block_present_surfaces.push(present_ids);
    }

    let mut stats = Vec::new();
    for (surface_id, accumulator) in surface_index.accumulators.iter().enumerate() {
        if accumulator.raw_occurrences < min_occurrences || accumulator.block_count < min_blocks {
            continue;
        }
        let left_entropy = entropy(&accumulator.left_contexts);
        let right_entropy = entropy(&accumulator.right_contexts);
        let boundary_entropy = left_entropy.min(right_entropy);
        let surface = surface_index.names[surface_id].as_str();
        if boundary_entropy < ZH_BLOCK_MIN_BOUNDARY_ENTROPY
            && !seed_name_set.contains(surface)
            && strip_zh_person_name_trailing_noise(surface).is_none()
            && !is_trusted_low_entropy_suffix_extension(surface, &seed_name_set)
        {
            continue;
        }
        let char_len = surface.chars().count();
        stats.push(RepeatedSpanSurfaceStat {
            surface_id,
            char_len,
            raw_occurrences: accumulator.raw_occurrences,
            block_count: accumulator.block_count,
            left_entropy,
            right_entropy,
            discovery_score: surface_discovery_score(
                surface,
                char_len,
                accumulator.raw_occurrences,
                accumulator.block_count,
                left_entropy,
                right_entropy,
            ),
        });
    }

    stats.sort_unstable_by(|left, right| {
        right
            .discovery_score
            .total_cmp(&left.discovery_score)
            .then_with(|| right.block_count.cmp(&left.block_count))
            .then_with(|| right.raw_occurrences.cmp(&left.raw_occurrences))
            .then_with(|| right.char_len.cmp(&left.char_len))
            .then_with(|| {
                surface_index.names[left.surface_id].cmp(&surface_index.names[right.surface_id])
            })
    });

    Ok((surface_index, stats, block_present_surfaces))
}

fn record_local_seed_extensions(
    surface_index: &mut SurfaceIndex,
    pass: &mut BlockPass<'_>,
    seed_surface: &str,
    start_char: usize,
    end_char: usize,
    block_text: &str,
    char_starts: &[usize],
) {
    let chars = pass.chars;
    let seed_char_len = end_char.saturating_sub(start_char);
    let extension_budget = local_extension_budget(seed_surface, seed_char_len);
    if extension_budget == 0 {
        return;
    }

    let mut run_start = start_char;
    while run_start > 0 && is_cjk_name_char(chars[run_start - 1]) {
        run_start -= 1;
    }
    let mut run_end = end_char;
    while run_end < chars.len() && is_cjk_name_char(chars[run_end]) {
        run_end += 1;
    }
    let max_prefix = usize::min(start_char.saturating_sub(run_start), extension_budget);
    let max_suffix = usize::min(run_end.saturating_sub(end_char), extension_budget);
    let allow_prefix_extensions = allows_prefix_local_extensions(seed_surface);
    let allow_suffix_extensions = allows_suffix_local_extensions(seed_surface);
    let allow_bidirectional = allows_bidirectional_local_extensions(seed_surface);

    for prefix_extra in 0..=max_prefix {
        for suffix_extra in 0..=max_suffix {
            if prefix_extra == 0 && suffix_extra == 0 {
                continue;
            }
            if prefix_extra + suffix_extra > extension_budget {
                continue;
            }
            if prefix_extra > 0 && !allow_prefix_extensions {
                continue;
            }
            if suffix_extra > 0 && !allow_suffix_extensions {
                continue;
            }
            if prefix_extra > 0 && suffix_extra > 0 && !allow_bidirectional {
                continue;
            }
            if !allows_specific_local_extension(
                seed_surface,
                prefix_extra,
                suffix_extra,
                chars.get(end_char).copied(),
            ) {
                continue;
            }

            let surface_start = start_char - prefix_extra;
            let surface_end = end_char + suffix_extra;
            let surface = &block_text[char_starts[surface_start]..char_starts[surface_end]];
            surface_index.record_occurrence(pass, surface, surface_start, surface_end, false);
        }
    }
}

fn local_extension_budget(surface: &str, char_len: usize) -> usize {
    if char_len == 0 {
        return 0;
    }
    if is_short_translit_fragment(surface)
        || is_zh_compound_surname(surface)
        || is_generic_two_char_extension_seed(surface)
    {
        ZH_BLOCK_LOCAL_EXTENSION_MAX_EXTRA_CHARS
    } else {
        1
    }
}

fn looks_like_person_extension_seed(surface: &str) -> bool {
    looks_like_person_like_surface(surface) || is_zh_compound_surname(surface)
}

fn is_generic_two_char_extension_seed(surface: &str) -> bool {
    surface.chars().count() == 2
        && !looks_like_person_extension_seed(surface)
        && !is_short_translit_fragment(surface)
}

fn is_generic_prefix_char(ch: char) -> bool {
    ZH_BLOCK_GENERIC_MODIFIER_PREFIX_CHARS.contains(ch)
        || ZH_BLOCK_LOW_VALUE_PREFIX_CHARS.contains(ch)
        || ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS.contains(ch)
}

fn is_generic_suffix_char(ch: char) -> bool {
    ZH_BLOCK_LOW_VALUE_SUFFIX_CHARS.contains(ch)
        || ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS.contains(ch)
        || is_zh_name_trailing_block_char(ch)
}

fn has_low_value_generic_prefix(surface: &str) -> bool {
    surface.chars().next().is_some_and(is_generic_prefix_char)
}

/// Allow a low-entropy 3-4 char surface when it extends a known generic
/// two-char seed in a trusted way (e.g. role suffixes like 帝/王/师).
fn is_trusted_low_entropy_suffix_extension(
    surface: &str,
    seed_name_set: &FxHashSet<String>,
) -> bool {
    let char_len = surface.chars().count();
    if !(3..=4).contains(&char_len) {
        return false;
    }

    for removed_chars in 1..=2 {
        if char_len <= removed_chars {
            continue;
        }
        let Some(seed_surface) = prefix_chars(surface, char_len - removed_chars) else {
            continue;
        };
        if !seed_name_set.contains(seed_surface)
            || !is_generic_two_char_extension_seed(seed_surface)
        {
            continue;
        }
        if !has_low_value_generic_prefix(seed_surface) {
            return true;
        }
        let Some(added_fragment) =
            suffix_after_removing_prefix_chars(surface, seed_surface.chars().count())
        else {
            continue;
        };
        if added_fragment
            .chars()
            .next()
            .is_some_and(|ch| ZH_BLOCK_GENERIC_ROLE_SUFFIX_CHARS.contains(ch))
        {
            return true;
        }
    }

    false
}

fn allows_suffix_local_extensions(surface: &str) -> bool {
    looks_like_person_extension_seed(surface)
        || is_short_translit_fragment(surface)
        || is_generic_two_char_extension_seed(surface)
}

fn allows_prefix_local_extensions(surface: &str) -> bool {
    if is_short_translit_fragment(surface) || is_zh_name_suffix_title(surface) {
        return true;
    }
    !looks_like_person_extension_seed(surface) && surface.chars().count() <= 3
}

fn allows_bidirectional_local_extensions(surface: &str) -> bool {
    is_short_translit_fragment(surface) || is_zh_name_suffix_title(surface)
}

fn allows_specific_local_extension(
    seed_surface: &str,
    prefix_extra: usize,
    suffix_extra: usize,
    next_char: Option<char>,
) -> bool {
    if prefix_extra > 0 && suffix_extra > 0 {
        return true;
    }
    if suffix_extra == 0 {
        return true;
    }
    if is_zh_compound_surname(seed_surface) || is_short_translit_fragment(seed_surface) {
        return true;
    }
    if is_generic_two_char_extension_seed(seed_surface) {
        return next_char.is_some_and(|ch| {
            !is_generic_suffix_char(ch)
                && (!has_low_value_generic_prefix(seed_surface)
                    || ZH_BLOCK_GENERIC_ROLE_SUFFIX_CHARS.contains(ch))
        });
    }
    if !looks_like_person_like_surface(seed_surface) {
        return true;
    }
    next_char.is_some_and(is_generic_suffix_char)
}

fn normalize_boundary_symbol(ch: char) -> BoundarySymbol {
    if ch.is_whitespace() {
        BoundarySymbol::Whitespace
    } else if !ch.is_alphanumeric() && !is_cjk_name_char(ch) {
        BoundarySymbol::Punctuation
    } else {
        BoundarySymbol::Char(ch)
    }
}

fn entropy(counter: &FxHashMap<BoundarySymbol, CandidateCount>) -> f64 {
    let total = counter.values().map(|count| *count as usize).sum::<usize>();
    if total == 0 {
        return 0.0;
    }
    counter
        .values()
        .filter(|count| **count > 0)
        .map(|count| {
            let probability = (*count as f64) / (total as f64);
            -probability * probability.log2()
        })
        .sum()
}

fn is_low_value_surface(surface: &str, common_words: &FxHashSet<String>) -> bool {
    if surface.is_empty() {
        return true;
    }
    if common_words.contains(surface) {
        return true;
    }
    if all_same_chars(surface) {
        return true;
    }

    let char_len = surface.chars().count();
    if char_len == 2 && !looks_like_two_char_name(surface) {
        let first_char = surface.chars().next().unwrap_or_default();
        let last_char = surface.chars().last().unwrap_or_default();
        if !ZH_BLOCK_TWO_CHAR_HINT_SUFFIXES.contains(last_char)
            && (ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS.contains(first_char)
                || ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS.contains(last_char))
        {
            return true;
        }
    }

    if char_len <= 4
        && surface
            .chars()
            .any(|ch| ZH_BLOCK_LOW_VALUE_INTERIOR_CHARS.contains(ch))
        && !looks_like_zh_person_name(surface)
    {
        return true;
    }

    if char_len >= 3
        && surface
            .chars()
            .next()
            .is_some_and(|ch| ZH_BLOCK_LOW_VALUE_PREFIX_CHARS.contains(ch))
    {
        return true;
    }

    if char_len >= 3
        && surface
            .chars()
            .last()
            .is_some_and(|ch| ZH_BLOCK_LOW_VALUE_SUFFIX_CHARS.contains(ch))
    {
        return true;
    }

    false
}

fn looks_like_two_char_name(surface: &str) -> bool {
    let mut chars = surface.chars();
    let (Some(first_char), Some(last_char), None) = (chars.next(), chars.next(), chars.next())
    else {
        return false;
    };
    (is_zh_single_surname_char(first_char) || ZH_BLOCK_EXTRA_SINGLE_SURNAMES.contains(first_char))
        && !ZH_BLOCK_TWO_CHAR_FUNCTION_CHARS.contains(last_char)
}

fn looks_like_person_like_surface(surface: &str) -> bool {
    looks_like_zh_person_name(surface) || looks_like_two_char_name(surface)
}

fn surface_discovery_score(
    surface: &str,
    char_len: usize,
    raw_occurrences: usize,
    block_count: usize,
    left_entropy: f64,
    right_entropy: f64,
) -> f64 {
    left_entropy.min(right_entropy) * 2.0
        + (raw_occurrences as f64 + 1.0).ln() * 2.2
        + (block_count as f64 + 1.0).ln() * 2.8
        + surface_shape_bonus(surface, char_len)
}

fn surface_shape_bonus(surface: &str, char_len: usize) -> f64 {
    let mut bonus = 0.0;
    if looks_like_person_like_surface(surface) {
        bonus += 3.0;
    }
    if char_len >= 3 {
        bonus += 1.0;
    } else if surface
        .chars()
        .last()
        .is_some_and(|ch| ZH_BLOCK_TWO_CHAR_HINT_SUFFIXES.contains(ch))
    {
        bonus += 1.25;
    } else {
        bonus -= 1.0;
    }
    if strip_zh_person_name_trailing_noise(surface).is_some() {
        bonus -= 1.5;
    }
    bonus
}

fn build_canonical_candidates(
    surface_names: &[String],
    surface_stats: &[RepeatedSpanSurfaceStat],
    surface_blocks: &[Vec<usize>],
) -> Vec<CanonicalCandidate> {
    if surface_stats.is_empty() {
        return Vec::new();
    }

    let stats_by_id: FxHashMap<usize, &RepeatedSpanSurfaceStat> = surface_stats
        .iter()
        .map(|stat| (stat.surface_id, stat))
        .collect();
    let surface_id_by_name: FxHashMap<String, usize> = surface_names
        .iter()
        .enumerate()
        .map(|(surface_id, surface)| (surface.clone(), surface_id))
        .collect();
    let mut dominant_extensions = dominant_extension_map(
        surface_names,
        surface_stats,
        &stats_by_id,
        &surface_id_by_name,
        surface_blocks,
    );
    dominant_extensions.extend(generic_surface_family_map(
        surface_names,
        surface_stats,
        &stats_by_id,
        &surface_id_by_name,
        surface_blocks,
    ));
    dominant_extensions.extend(low_value_affix_surface_map(
        surface_names,
        &surface_id_by_name,
    ));

    let mut grouped_surfaces: FxHashMap<usize, Vec<usize>> = FxHashMap::default();
    for stat in surface_stats {
        let canonical_id = resolve_canonical_surface(stat.surface_id, &dominant_extensions);
        grouped_surfaces
            .entry(canonical_id)
            .or_default()
            .push(stat.surface_id);
    }

    let mut canonical_candidates = Vec::new();
    for (canonical_id, mut cluster_surface_ids) in grouped_surfaces {
        let mut cluster_blocks: FxHashSet<usize> = FxHashSet::default();
        let mut raw_occurrences = 0usize;
        let mut discovery_score = 0.0f64;
        for surface_id in &cluster_surface_ids {
            if let Some(stat) = stats_by_id.get(surface_id) {
                raw_occurrences += stat.raw_occurrences;
                discovery_score = discovery_score.max(stat.discovery_score);
            }
            for block_id in &surface_blocks[*surface_id] {
                cluster_blocks.insert(*block_id);
            }
        }
        let block_count = cluster_blocks.len();
        if block_count < ZH_BLOCK_MIN_BLOCKS {
            continue;
        }
        cluster_surface_ids.sort_unstable_by(|left, right| {
            let left_stat = stats_by_id
                .get(left)
                .copied()
                .expect("missing left surface stat");
            let right_stat = stats_by_id
                .get(right)
                .copied()
                .expect("missing right surface stat");
            (*left != canonical_id)
                .cmp(&(*right != canonical_id))
                .then_with(|| {
                    right_stat
                        .discovery_score
                        .total_cmp(&left_stat.discovery_score)
                })
                .then_with(|| right_stat.char_len.cmp(&left_stat.char_len))
                .then_with(|| surface_names[*left].cmp(&surface_names[*right]))
        });
        let importance = block_count + usize::min(raw_occurrences / 2, block_count);
        canonical_candidates.push(CanonicalCandidate {
            canonical_id,
            importance,
            block_count,
            discovery_score: discovery_score
                + (cluster_surface_ids.len().saturating_sub(1) as f64) * 0.1,
            surface_ids: cluster_surface_ids,
        });
    }

    canonical_candidates.sort_unstable_by(|left, right| {
        let left_len = stats_by_id
            .get(&left.canonical_id)
            .map(|stat| stat.char_len)
            .unwrap_or(0);
        let right_len = stats_by_id
            .get(&right.canonical_id)
            .map(|stat| stat.char_len)
            .unwrap_or(0);
        right
            .discovery_score
            .total_cmp(&left.discovery_score)
            .then_with(|| right.importance.cmp(&left.importance))
            .then_with(|| right.block_count.cmp(&left.block_count))
            .then_with(|| right_len.cmp(&left_len))
            .then_with(|| surface_names[left.canonical_id].cmp(&surface_names[right.canonical_id]))
    });

    canonical_candidates
}

/// Fold "prefix-noise + surface" / "surface + suffix-noise" variants onto the
/// bare surface when both were observed.
fn low_value_affix_surface_map(
    surface_names: &[String],
    surface_id_by_name: &FxHashMap<String, usize>,
) -> FxHashMap<usize, usize> {
    let mut families = FxHashMap::default();

    for (surface_id, surface) in surface_names.iter().enumerate() {
        let char_len = surface.chars().count();
        if char_len < 3 {
            continue;
        }

        let first_char = surface.chars().next().unwrap_or_default();
        if is_generic_prefix_char(first_char) {
            if let Some(stripped) = suffix_after_removing_prefix_chars(surface, 1) {
                if let Some(&canonical_id) = surface_id_by_name.get(stripped) {
                    families.insert(surface_id, canonical_id);
                    continue;
                }
            }
        }

        let last_char = surface.chars().last().unwrap_or_default();
        if is_generic_suffix_char(last_char) {
            if let Some(stripped) = prefix_chars(surface, char_len - 1) {
                if let Some(&canonical_id) = surface_id_by_name.get(stripped) {
                    families.insert(surface_id, canonical_id);
                }
            }
        }
    }

    families
}

/// Map person-shaped short surfaces onto their dominant longer extension when
/// one extension clearly contains the short form's blocks.
fn dominant_extension_map(
    surface_names: &[String],
    surface_stats: &[RepeatedSpanSurfaceStat],
    stats_by_id: &FxHashMap<usize, &RepeatedSpanSurfaceStat>,
    surface_id_by_name: &FxHashMap<String, usize>,
    surface_blocks: &[Vec<usize>],
) -> FxHashMap<usize, usize> {
    let person_extension_options =
        build_person_extension_options(surface_names, surface_id_by_name);
    let mut dominant = FxHashMap::default();

    for stat in surface_stats {
        let surface_id = stat.surface_id;
        let surface = surface_names[surface_id].as_str();
        let blocks = &surface_blocks[surface_id];
        if blocks.is_empty() {
            continue;
        }

        if let Some(canonical) = strip_zh_person_name_trailing_noise(surface) {
            if let Some(&canonical_id) = surface_id_by_name.get(canonical) {
                dominant.insert(surface_id, canonical_id);
                continue;
            }
        }

        if blocks.len() <= 1 || !looks_like_person_like_surface(surface) {
            continue;
        }

        let mut seen_options: FxHashSet<usize> = FxHashSet::default();
        let mut options: Vec<(f64, f64, usize)> = Vec::new();
        if let Some(candidate_ids) = person_extension_options.get(&surface_id) {
            for &other_id in candidate_ids {
                if !seen_options.insert(other_id) || other_id == surface_id {
                    continue;
                }
                let other_surface = surface_names[other_id].as_str();
                if strip_zh_person_name_trailing_noise(other_surface) == Some(surface) {
                    continue;
                }
                let Some(other_stat) = stats_by_id.get(&other_id).copied() else {
                    continue;
                };
                if other_stat.left_entropy.min(other_stat.right_entropy)
                    < ZH_BLOCK_MIN_BOUNDARY_ENTROPY
                {
                    continue;
                }
                let overlap = count_sorted_overlap(blocks, &surface_blocks[other_id]);
                if overlap == 0 {
                    continue;
                }
                let containment = overlap as f64 / blocks.len().max(1) as f64;
                if containment < ZH_BLOCK_MIN_EXTENSION_CONTAINMENT {
                    continue;
                }
                let specificity = other_stat.discovery_score
                    + (other_stat.char_len.saturating_sub(stat.char_len) as f64) * 0.5;
                options.push((specificity, containment, other_id));
            }
        }
        if options.is_empty() {
            continue;
        }

        options.sort_unstable_by(|left, right| {
            let left_stat = stats_by_id
                .get(&left.2)
                .copied()
                .expect("missing dominant left stat");
            let right_stat = stats_by_id
                .get(&right.2)
                .copied()
                .expect("missing dominant right stat");
            right
                .0
                .total_cmp(&left.0)
                .then_with(|| right.1.total_cmp(&left.1))
                .then_with(|| right_stat.char_len.cmp(&left_stat.char_len))
                .then_with(|| surface_names[left.2].cmp(&surface_names[right.2]))
        });
        let best_score = options[0].0;
        let second_score = options
            .get(1)
            .map(|item| item.0)
            .unwrap_or(f64::NEG_INFINITY);
        if best_score - second_score < ZH_BLOCK_MIN_EXTENSION_SCORE_MARGIN {
            continue;
        }
        dominant.insert(surface_id, options[0].2);
    }

    dominant
}

/// Group non-person fragments with their unambiguous one-char extensions,
/// choosing direction by which side carries the noise char.
fn generic_surface_family_map(
    surface_names: &[String],
    surface_stats: &[RepeatedSpanSurfaceStat],
    stats_by_id: &FxHashMap<usize, &RepeatedSpanSurfaceStat>,
    surface_id_by_name: &FxHashMap<String, usize>,
    surface_blocks: &[Vec<usize>],
) -> FxHashMap<usize, usize> {
    let (prefix_extensions, suffix_extensions) =
        build_one_char_extension_options(surface_names, surface_id_by_name);
    let mut families = FxHashMap::default();

    for stat in surface_stats {
        let surface_id = stat.surface_id;
        if families.contains_key(&surface_id)
            || looks_like_zh_person_name(&surface_names[surface_id])
        {
            continue;
        }

        if let Some(best_prefix_extension) = best_generic_extension(
            surface_id,
            true,
            &prefix_extensions,
            stats_by_id,
            surface_names,
            surface_blocks,
        ) {
            let prefix_char = surface_names[best_prefix_extension]
                .chars()
                .next()
                .unwrap_or_default();
            if is_generic_prefix_char(prefix_char) {
                families.insert(best_prefix_extension, surface_id);
            } else {
                families.insert(surface_id, best_prefix_extension);
            }
            continue;
        }

        if let Some(best_suffix_extension) = best_generic_extension(
            surface_id,
            false,
            &suffix_extensions,
            stats_by_id,
            surface_names,
            surface_blocks,
        ) {
            let suffix_char = surface_names[best_suffix_extension]
                .chars()
                .last()
                .unwrap_or_default();
            if is_generic_suffix_char(suffix_char) {
                families.insert(best_suffix_extension, surface_id);
            } else {
                families.insert(surface_id, best_suffix_extension);
            }
        }
    }

    families
}

fn best_generic_extension(
    surface_id: usize,
    choose_prefix_extension: bool,
    extension_options: &FxHashMap<usize, Vec<usize>>,
    stats_by_id: &FxHashMap<usize, &RepeatedSpanSurfaceStat>,
    surface_names: &[String],
    surface_blocks: &[Vec<usize>],
) -> Option<usize> {
    let stat = stats_by_id.get(&surface_id).copied()?;
    let blocks = &surface_blocks[surface_id];
    if stat.char_len < 2 || blocks.is_empty() {
        return None;
    }

    let directional_entropy = if choose_prefix_extension {
        stat.left_entropy
    } else {
        stat.right_entropy
    };
    if directional_entropy > ZH_BLOCK_FRAGMENT_DIRECTIONAL_ENTROPY_MAX {
        return None;
    }

    let mut seen_options: FxHashSet<usize> = FxHashSet::default();
    let mut options: Vec<(f64, usize, usize)> = Vec::new();
    if let Some(candidate_ids) = extension_options.get(&surface_id) {
        for &other_id in candidate_ids {
            if !seen_options.insert(other_id) || other_id == surface_id {
                continue;
            }
            let overlap = count_sorted_overlap(blocks, &surface_blocks[other_id]);
            let containment = overlap as f64 / blocks.len().max(1) as f64;
            if containment < ZH_BLOCK_FRAGMENT_EXTENSION_MIN_CONTAINMENT {
                continue;
            }
            options.push((containment, overlap, other_id));
        }
    }
    if options.is_empty() {
        return None;
    }

    options.sort_unstable_by(|left, right| {
        let left_len = stats_by_id
            .get(&left.2)
            .map(|stat| stat.char_len)
            .unwrap_or(0);
        let right_len = stats_by_id
            .get(&right.2)
            .map(|stat| stat.char_len)
            .unwrap_or(0);
        right
            .0
            .total_cmp(&left.0)
            .then_with(|| right.1.cmp(&left.1))
            .then_with(|| right_len.cmp(&left_len))
            .then_with(|| surface_names[left.2].cmp(&surface_names[right.2]))
    });
    let best_surface = options[0].2;
    let best_overlap = options[0].1;
    let second_overlap = options.get(1).map(|item| item.1).unwrap_or(0);
    if second_overlap > 0
        && (second_overlap as f64 / best_overlap.max(1) as f64)
            >= ZH_BLOCK_FRAGMENT_EXTENSION_MAX_SECONDARY_RATIO
    {
        return None;
    }
    Some(best_surface)
}

fn build_person_extension_options(
    surface_names: &[String],
    surface_id_by_name: &FxHashMap<String, usize>,
) -> FxHashMap<usize, Vec<usize>> {
    let mut options: FxHashMap<usize, Vec<usize>> = FxHashMap::default();

    for (other_id, other_name) in surface_names.iter().enumerate() {
        if !looks_like_zh_person_name(other_name) {
            continue;
        }
        let char_len = other_name.chars().count();
        for removed_chars in 1..=2 {
            if char_len <= removed_chars {
                continue;
            }
            let mut seen_short_ids: FxHashSet<usize> = FxHashSet::default();
            if let Some(short_name) = prefix_chars(other_name, char_len - removed_chars) {
                if let Some(&short_id) = surface_id_by_name.get(short_name) {
                    if seen_short_ids.insert(short_id) {
                        options.entry(short_id).or_default().push(other_id);
                    }
                }
            }
            if let Some(short_name) = suffix_after_removing_prefix_chars(other_name, removed_chars)
            {
                if let Some(&short_id) = surface_id_by_name.get(short_name) {
                    if seen_short_ids.insert(short_id) {
                        options.entry(short_id).or_default().push(other_id);
                    }
                }
            }
        }
    }

    options
}

fn build_one_char_extension_options(
    surface_names: &[String],
    surface_id_by_name: &FxHashMap<String, usize>,
) -> (FxHashMap<usize, Vec<usize>>, FxHashMap<usize, Vec<usize>>) {
    let mut prefix_extensions: FxHashMap<usize, Vec<usize>> = FxHashMap::default();
    let mut suffix_extensions: FxHashMap<usize, Vec<usize>> = FxHashMap::default();

    for (other_id, other_name) in surface_names.iter().enumerate() {
        let char_len = other_name.chars().count();
        if char_len <= 1 {
            continue;
        }
        if let Some(short_name) = suffix_after_removing_prefix_chars(other_name, 1) {
            if let Some(&short_id) = surface_id_by_name.get(short_name) {
                prefix_extensions
                    .entry(short_id)
                    .or_default()
                    .push(other_id);
            }
        }
        if let Some(short_name) = prefix_chars(other_name, char_len - 1) {
            if let Some(&short_id) = surface_id_by_name.get(short_name) {
                suffix_extensions
                    .entry(short_id)
                    .or_default()
                    .push(other_id);
            }
        }
    }

    (prefix_extensions, suffix_extensions)
}

fn resolve_canonical_surface(
    surface_id: usize,
    dominant_extensions: &FxHashMap<usize, usize>,
) -> usize {
    let mut current = surface_id;
    let mut seen: FxHashSet<usize> = FxHashSet::default();
    seen.insert(current);
    while let Some(next) = dominant_extensions.get(&current).copied() {
        if !seen.insert(next) {
            break;
        }
        current = next;
    }
    current
}

fn compact_selected_candidates_output(
    surface_names: &[String],
    selected_candidates: &[CanonicalCandidate],
    block_present_surfaces: &[Vec<usize>],
) -> CompactRefinementOutput {
    if selected_candidates.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    }

    let mut surface_to_canonical = vec![None; surface_names.len()];
    for candidate in selected_candidates {
        for &surface_id in &candidate.surface_ids {
            surface_to_canonical[surface_id] = Some(candidate.canonical_id);
        }
    }

    let mut pair_counts: FxHashMap<(usize, usize), usize> = FxHashMap::default();
    let mut present_canonicals = Vec::new();
    for present_surface_ids in block_present_surfaces {
        present_canonicals.clear();
        for &surface_id in present_surface_ids {
            if let Some(canonical_id) = surface_to_canonical[surface_id] {
                present_canonicals.push(canonical_id);
            }
        }
        if present_canonicals.len() < 2 {
            continue;
        }
        present_canonicals.sort_unstable();
        present_canonicals.dedup();
        for index in 0..present_canonicals.len() {
            let left_id = present_canonicals[index];
            for &right_id in &present_canonicals[index + 1..] {
                *pair_counts.entry((left_id, right_id)).or_insert(0) += 1;
            }
        }
    }

    let mut local_to_compact = vec![usize::MAX; surface_names.len()];
    let mut compact_names = Vec::new();
    let mut importance_items = Vec::with_capacity(selected_candidates.len());
    let mut canonical_surface_items = Vec::with_capacity(selected_candidates.len());

    for candidate in selected_candidates {
        let compact_canonical_id = ensure_compact_surface_id(
            candidate.canonical_id,
            surface_names,
            &mut local_to_compact,
            &mut compact_names,
        );
        importance_items.push((compact_canonical_id, candidate.importance));
        let mut compact_surface_ids = Vec::with_capacity(candidate.surface_ids.len());
        for &surface_id in &candidate.surface_ids {
            compact_surface_ids.push(ensure_compact_surface_id(
                surface_id,
                surface_names,
                &mut local_to_compact,
                &mut compact_names,
            ));
        }
        canonical_surface_items.push((compact_canonical_id, compact_surface_ids));
    }

    let mut pair_items = pair_counts.into_iter().collect::<Vec<_>>();
    pair_items.sort_unstable_by(|left, right| {
        right
            .1
            .cmp(&left.1)
            .then_with(|| surface_names[left.0 .0].cmp(&surface_names[right.0 .0]))
            .then_with(|| surface_names[left.0 .1].cmp(&surface_names[right.0 .1]))
    });
    let compact_pairs = pair_items
        .into_iter()
        .map(|((left_id, right_id), count)| {
            (
                ensure_compact_surface_id(
                    left_id,
                    surface_names,
                    &mut local_to_compact,
                    &mut compact_names,
                ),
                ensure_compact_surface_id(
                    right_id,
                    surface_names,
                    &mut local_to_compact,
                    &mut compact_names,
                ),
                count,
            )
        })
        .collect();

    (
        compact_names,
        importance_items,
        compact_pairs,
        canonical_surface_items,
    )
}

fn ensure_compact_surface_id(
    surface_id: usize,
    surface_names: &[String],
    local_to_compact: &mut [usize],
    compact_names: &mut Vec<String>,
) -> usize {
    if local_to_compact[surface_id] != usize::MAX {
        return local_to_compact[surface_id];
    }
    let compact_id = compact_names.len();
    compact_names.push(surface_names[surface_id].clone());
    local_to_compact[surface_id] = compact_id;
    compact_id
}

fn count_sorted_overlap(left: &[usize], right: &[usize]) -> usize {
    let mut left_idx = 0usize;
    let mut right_idx = 0usize;
    let mut overlap = 0usize;
    while left_idx < left.len() && right_idx < right.len() {
        match left[left_idx].cmp(&right[right_idx]) {
            std::cmp::Ordering::Less => left_idx += 1,
            std::cmp::Ordering::Greater => right_idx += 1,
            std::cmp::Ordering::Equal => {
                overlap += 1;
                left_idx += 1;
                right_idx += 1;
            }
        }
    }
    overlap
}
