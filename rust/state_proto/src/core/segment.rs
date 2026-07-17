use super::*;
use std::sync::LazyLock;

static BLANK_LINE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\n[ \t]*\n(?:[ \t]*\n)+").expect("blank-line regex"));
static BLANK_PARAGRAPH_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\n\s*\n").expect("blank paragraph regex"));

pub(crate) fn normalize_chapter_text(text: &str) -> String {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    BLANK_LINE_RE
        .replace_all(&normalized, "\n\n")
        .trim()
        .to_owned()
}

pub(crate) fn pack_segment_id(chapter_id: i64, local_ordinal: i64) -> i64 {
    (chapter_id << STATE_PROTO_SEGMENT_ID_SHIFT) | local_ordinal
}

pub(crate) fn pack_claim_id(chapter_id: i64, local_ordinal: i64) -> i64 {
    (chapter_id << STATE_PROTO_CLAIM_ID_SHIFT) | local_ordinal
}

pub(crate) fn segment_chapter_text(
    chapter_id: i64,
    chapter_number: i64,
    indexed: &IndexedText,
) -> Vec<SegmentData> {
    if indexed.char_len() == 0 {
        return Vec::new();
    }
    let script_mode = detect_script_mode(&indexed.chars);
    let boundaries = preferred_boundaries(indexed, script_mode);
    let ranges = build_segment_ranges(indexed.char_len(), &boundaries);
    materialize_segment_rows(chapter_id, chapter_number, ranges)
}

pub(crate) fn segment_chapter_text_without_index(
    chapter_id: i64,
    chapter_number: i64,
    text: &str,
) -> Vec<SegmentData> {
    if text.is_empty() {
        return Vec::new();
    }

    let mut char_to_byte = Vec::new();
    let mut total = 0usize;
    let mut cjk_count = 0usize;
    for (byte_idx, ch) in text.char_indices() {
        char_to_byte.push(byte_idx);
        if !ch.is_whitespace() {
            total += 1;
            if is_cjk(ch) {
                cjk_count += 1;
            }
        }
    }
    if char_to_byte.is_empty() {
        return Vec::new();
    }
    char_to_byte.push(text.len());

    let script_mode = if total == 0 {
        SCRIPT_MODE_SPACE_DELIMITED
    } else if (cjk_count as f64) / (total as f64) >= 0.30 {
        SCRIPT_MODE_CJK_HEAVY
    } else {
        SCRIPT_MODE_SPACE_DELIMITED
    };

    let mut boundaries = Vec::new();
    for matched in BLANK_PARAGRAPH_RE.find_iter(text) {
        boundaries.push(byte_to_char_index(&char_to_byte, matched.end()));
    }
    append_sentence_boundaries(text, script_mode, &mut boundaries);
    boundaries.sort_unstable();
    boundaries.dedup();

    let ranges = build_segment_ranges(char_to_byte.len() - 1, &boundaries);
    materialize_segment_rows(chapter_id, chapter_number, ranges)
}

fn preferred_boundaries(indexed: &IndexedText, script_mode: &str) -> Vec<usize> {
    let mut boundaries = Vec::new();
    for matched in BLANK_PARAGRAPH_RE.find_iter(&indexed.text) {
        boundaries.push(indexed.byte_to_char(matched.end()));
    }
    append_sentence_boundaries(&indexed.text, script_mode, &mut boundaries);
    boundaries.sort_unstable();
    boundaries.dedup();
    boundaries
}

fn first_boundary_in_range(boundaries: &[usize], lower: usize, upper: usize) -> Option<usize> {
    let start = boundaries.partition_point(|boundary| *boundary < lower);
    let boundary = boundaries.get(start).copied()?;
    (boundary <= upper).then_some(boundary)
}

fn append_sentence_boundaries(text: &str, script_mode: &str, boundaries: &mut Vec<usize>) {
    let terminators = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        CJK_SENTENCE_TERMINATORS
    } else {
        NON_CJK_SENTENCE_TERMINATORS
    };
    let mut pending_boundary: Option<usize> = None;
    for (char_idx, ch) in text.chars().enumerate() {
        if let Some(boundary) = pending_boundary {
            if SENTENCE_CLOSERS.contains(&ch) {
                pending_boundary = Some(char_idx + 1);
                continue;
            }
            boundaries.push(boundary);
            pending_boundary = None;
        }
        if terminators.contains(&ch) {
            pending_boundary = Some(char_idx + 1);
        }
    }
    if let Some(boundary) = pending_boundary {
        boundaries.push(boundary);
    }
}

fn byte_to_char_index(char_to_byte: &[usize], byte_idx: usize) -> usize {
    match char_to_byte.binary_search(&byte_idx) {
        Ok(idx) => idx,
        Err(idx) => idx,
    }
}

fn build_segment_ranges(text_length: usize, boundaries: &[usize]) -> Vec<(usize, usize)> {
    let mut segments = Vec::new();
    let mut start = 0usize;
    while start < text_length {
        let remaining = text_length - start;
        if remaining <= DEFAULT_SEGMENT_HARD_MAX_CHARS {
            segments.push((start, text_length));
            break;
        }
        let lower = start + DEFAULT_SEGMENT_MIN_CHARS;
        let soft = usize::min(start + DEFAULT_SEGMENT_SOFT_MAX_CHARS, text_length);
        let hard = usize::min(start + DEFAULT_SEGMENT_HARD_MAX_CHARS, text_length);
        let mut chosen = first_boundary_in_range(boundaries, lower, soft);
        if chosen.is_none() {
            chosen = first_boundary_in_range(boundaries, soft + 1, hard);
        }
        let chosen = chosen.unwrap_or(hard);
        segments.push((start, chosen));
        start = chosen;
    }

    if segments.len() >= 2 {
        let (tail_start, tail_end) = segments[segments.len() - 1];
        let tail_len = tail_end - tail_start;
        let (prev_start, _prev_end) = segments[segments.len() - 2];
        if tail_len < DEFAULT_SEGMENT_TAIL_MERGE_CHARS
            && tail_end - prev_start <= DEFAULT_SEGMENT_MERGED_MAX_CHARS
        {
            let last = segments.len() - 1;
            segments[last - 1] = (prev_start, tail_end);
            segments.pop();
        }
    }

    segments
}

fn materialize_segment_rows(
    chapter_id: i64,
    chapter_number: i64,
    ranges: Vec<(usize, usize)>,
) -> Vec<SegmentData> {
    let segment_base = pack_segment_id(chapter_id, 0);
    let total_segments = ranges.len();
    ranges
        .into_iter()
        .enumerate()
        .map(|(idx, (start_pos, end_pos))| {
            let local_ordinal = (idx + 1) as i64;
            SegmentData {
                segment_id: segment_base + local_ordinal,
                chapter_id,
                chapter_number,
                start_pos: start_pos as i64,
                end_pos: end_pos as i64,
                progress_bucket: 0,
                prev_segment_id: if idx > 0 {
                    Some(segment_base + idx as i64)
                } else {
                    None
                },
                next_segment_id: if idx + 1 < total_segments {
                    Some(segment_base + local_ordinal + 1)
                } else {
                    None
                },
            }
        })
        .collect()
}

pub(crate) fn detect_script_mode(chars: &[char]) -> &'static str {
    let mut total = 0usize;
    let mut cjk_count = 0usize;
    for ch in chars {
        if ch.is_whitespace() {
            continue;
        }
        total += 1;
        if is_cjk(*ch) {
            cjk_count += 1;
        }
    }
    if total == 0 {
        return SCRIPT_MODE_SPACE_DELIMITED;
    }
    if (cjk_count as f64) / (total as f64) >= 0.30 {
        SCRIPT_MODE_CJK_HEAVY
    } else {
        SCRIPT_MODE_SPACE_DELIMITED
    }
}

pub(crate) fn is_cjk_language(language: &str) -> bool {
    let base = language.split('-').next().unwrap_or(language);
    matches!(base, "zh" | "ja" | "ko")
}

pub(crate) fn is_cjk(ch: char) -> bool {
    matches!(ch as u32,
        0x3400..=0x4DBF |
        0x4E00..=0x9FFF |
        0xF900..=0xFAFF
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn segmentation_without_index_matches_indexed_path() {
        let samples = [
            "第一句。第二句”第三句。\n\n第四段。\n第五句",
            "A short paragraph.\n\nAnother one closes.) Final sentence!",
            "“云澈！”她喊道。云澈没有回头……\n \n绝云崖下，风声如泣。",
        ];

        for (chapter_id, sample) in samples.iter().enumerate() {
            let normalized = normalize_chapter_text(sample);
            let indexed = IndexedText::new(normalized.clone());
            let indexed_segments = segment_chapter_text(chapter_id as i64 + 1, 1, &indexed);
            let fast_segments =
                segment_chapter_text_without_index(chapter_id as i64 + 1, 1, &normalized);

            assert_eq!(indexed_segments.len(), fast_segments.len());
            for (left, right) in indexed_segments.iter().zip(fast_segments.iter()) {
                assert_eq!(left.segment_id, right.segment_id);
                assert_eq!(left.chapter_id, right.chapter_id);
                assert_eq!(left.chapter_number, right.chapter_number);
                assert_eq!(left.start_pos, right.start_pos);
                assert_eq!(left.end_pos, right.end_pos);
                assert_eq!(left.prev_segment_id, right.prev_segment_id);
                assert_eq!(left.next_segment_id, right.next_segment_id);
            }
        }
    }
}
