use super::*;

#[derive(Debug, Clone)]
pub(crate) struct AliasEntry {
    pub(crate) target_id: String,
    pub(crate) alias: String,
}

#[derive(Debug, Clone)]
pub(crate) struct AliasMatch {
    pub(crate) target_id: String,
    pub(crate) alias: String,
    pub(crate) start: usize,
    pub(crate) end: usize,
}

/// Alias matches grouped by segment id, then by target id.
pub(crate) type SegmentAliasMatches = HashMap<i64, HashMap<String, Vec<AliasMatch>>>;

pub(crate) fn build_mention_postings(
    segments: &[SegmentData],
    indexed: &IndexedText,
    context: &BuildContext,
) -> (Vec<MentionData>, SegmentAliasMatches) {
    let Some(alias_automaton) = context.alias_automaton.as_ref() else {
        return (Vec::new(), HashMap::new());
    };
    if segments.is_empty() || context.alias_entries.is_empty() {
        return (Vec::new(), HashMap::new());
    }

    let mut postings = Vec::new();
    let mut grouped_matches = HashMap::new();
    for segment in segments {
        let segment_text = indexed.slice(segment.start_pos as usize, segment.end_pos as usize);
        let matches = find_alias_matches(
            segment_text,
            segment.start_pos as usize,
            indexed.char_to_byte(segment.start_pos as usize),
            indexed,
            context.cjk_language,
            alias_automaton,
            &context.alias_entries,
        );
        let mut by_target: HashMap<String, Vec<AliasMatch>> = HashMap::new();
        for matched in matches {
            by_target
                .entry(matched.target_id.clone())
                .or_default()
                .push(matched);
        }
        let segment_char_len = usize::max((segment.end_pos - segment.start_pos) as usize, 1);
        for (target_id, target_matches) in &by_target {
            let density = (target_matches.len() as f64) / (segment_char_len as f64);
            let mention_score = (target_matches.len() as f64) + f64::min(2.0, density * 120.0);
            postings.push(MentionData {
                target_id: target_id.clone(),
                segment_id: segment.segment_id,
                mention_score: round_places(mention_score, 4),
                density: round_places(density, 6),
                best_anchor_offset: target_matches
                    .first()
                    .map(|item| item.start as i64)
                    .unwrap_or(0),
            });
        }
        if !by_target.is_empty() {
            grouped_matches.insert(segment.segment_id, by_target);
        }
    }
    (postings, grouped_matches)
}

fn find_alias_matches(
    text: &str,
    segment_start_char: usize,
    segment_start_byte: usize,
    indexed: &IndexedText,
    cjk_language: bool,
    alias_automaton: &AhoCorasick,
    alias_entries: &[AliasEntry],
) -> Vec<AliasMatch> {
    if text.is_empty() {
        return Vec::new();
    }
    let mut matches = Vec::new();
    for found in alias_automaton.find_overlapping_iter(text) {
        let entry = &alias_entries[found.pattern().as_usize()];
        let start_byte = found.start();
        let end_byte = found.end();
        if cjk_language || match_has_word_boundaries(text, start_byte, end_byte) {
            let start = indexed.byte_to_char(segment_start_byte + start_byte) - segment_start_char;
            let end = indexed.byte_to_char(segment_start_byte + end_byte) - segment_start_char;
            matches.push(AliasMatch {
                target_id: entry.target_id.clone(),
                alias: entry.alias.clone(),
                start,
                end,
            });
        }
    }
    matches.sort_by(|left, right| {
        (left.start, left.end, left.target_id.as_str()).cmp(&(
            right.start,
            right.end,
            right.target_id.as_str(),
        ))
    });
    matches
}

fn match_has_word_boundaries(text: &str, start_byte: usize, end_byte: usize) -> bool {
    fn is_word_char(ch: char) -> bool {
        ch.is_alphanumeric() || ch == '_' || ch == '-'
    }
    let left_ok = if start_byte == 0 {
        true
    } else {
        text[..start_byte]
            .chars()
            .next_back()
            .map(|ch| !is_word_char(ch))
            .unwrap_or(true)
    };
    let right_ok = if end_byte >= text.len() {
        true
    } else {
        text[end_byte..]
            .chars()
            .next()
            .map(|ch| !is_word_char(ch))
            .unwrap_or(true)
    };
    left_ok && right_ok
}
