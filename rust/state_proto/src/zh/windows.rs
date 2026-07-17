//! Sliding-window importance/co-occurrence summaries over shortlisted zh
//! candidates, using start/end event diffs instead of per-window rescans.

use aho_corasick::AhoCorasick;

use super::collect_char_starts_into;

/// `(candidate_names, per-candidate window counts, dense pair-count matrix)`.
pub(crate) type WindowCounts = (Vec<String>, Vec<usize>, Vec<u32>);
/// `(candidate_names, importance items, sorted co-occurrence pair items)`.
pub(crate) type CompactWindowItems = (Vec<String>, Vec<(usize, usize)>, Vec<(usize, usize, usize)>);

/// Per-candidate window-presence counts and a dense `candidate_count^2`
/// pair-count matrix (upper triangle populated, row-major).
pub(crate) fn summarize_window_counts(
    normalized_chapters: Vec<String>,
    mut shortlisted_candidates: Vec<String>,
    window_size: usize,
    window_step: usize,
) -> Result<WindowCounts, String> {
    if shortlisted_candidates.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new()));
    }

    shortlisted_candidates.sort_unstable();
    shortlisted_candidates.dedup();

    let window_size = window_size.max(1);
    let window_step = window_step.max(1);
    shortlisted_candidates.retain(|candidate| candidate.chars().count() <= window_size);
    if shortlisted_candidates.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new()));
    }

    let candidate_count = shortlisted_candidates.len();
    let candidate_char_lens: Vec<usize> = shortlisted_candidates
        .iter()
        .map(|candidate| candidate.chars().count())
        .collect();
    let pair_matrix_len = candidate_count
        .checked_mul(candidate_count)
        .ok_or_else(|| "candidate matrix too large".to_string())?;
    let automaton = AhoCorasick::new(&shortlisted_candidates).map_err(|err| err.to_string())?;
    let ascii_shortlist = shortlisted_candidates
        .iter()
        .all(|candidate| candidate.is_ascii());

    let mut importance_counts = vec![0usize; candidate_count];
    let mut pair_counts = vec![0u32; pair_matrix_len];
    let mut active_counts = vec![0u32; candidate_count];
    let mut active_ids = Vec::new();
    let mut active_listed = vec![false; candidate_count];
    let mut present_ids = Vec::new();
    let mut char_starts = Vec::new();
    let mut chapter_window_starts = Vec::new();
    let mut start_events: Vec<Vec<usize>> = Vec::new();
    let mut end_events: Vec<Vec<usize>> = Vec::new();

    for chapter in normalized_chapters {
        let chapter: &str = chapter.as_str();
        if chapter.trim().is_empty() {
            continue;
        }
        let ascii_chapter = chapter.is_ascii();
        let char_count = if ascii_chapter {
            chapter.len()
        } else {
            collect_char_starts_into(chapter, &mut char_starts);
            char_starts.len().saturating_sub(1)
        };
        if char_count == 0 {
            continue;
        }
        window_starts_into(
            char_count,
            window_size,
            window_step,
            &mut chapter_window_starts,
        );
        if chapter_window_starts.is_empty() {
            continue;
        }
        let window_count = chapter_window_starts.len();
        prepare_event_buckets(&mut start_events, window_count);
        prepare_event_buckets(&mut end_events, window_count + 1);
        if ascii_chapter && ascii_shortlist && candidate_count <= 64 {
            collect_ascii_window_events(
                chapter,
                &shortlisted_candidates,
                &candidate_char_lens,
                window_size,
                &chapter_window_starts,
                &mut start_events,
                &mut end_events,
            );
        } else {
            let mut char_cursor = 0usize;
            for mat in automaton.find_overlapping_iter(chapter) {
                let start_byte = mat.start();
                while char_cursor + 1 < char_starts.len()
                    && char_starts[char_cursor + 1] <= start_byte
                {
                    char_cursor += 1;
                }
                let candidate_id = mat.pattern().as_usize();
                let start_char = char_cursor;
                let end_char = start_char + candidate_char_lens[candidate_id];
                if end_char > char_count {
                    continue;
                }

                let min_window_start = end_char.saturating_sub(window_size);
                let max_window_start = start_char;
                let first_window_idx = chapter_window_starts
                    .partition_point(|&window_start| window_start < min_window_start);
                let end_window_idx = chapter_window_starts
                    .partition_point(|&window_start| window_start <= max_window_start);
                if first_window_idx >= end_window_idx {
                    continue;
                }
                start_events[first_window_idx].push(candidate_id);
                end_events[end_window_idx].push(candidate_id);
            }
        }

        active_ids.clear();
        active_counts.fill(0);
        active_listed.fill(false);
        for window_idx in 0..window_count {
            for &candidate_id in &end_events[window_idx] {
                active_counts[candidate_id] = active_counts[candidate_id]
                    .checked_sub(1)
                    .expect("window activity underflow");
            }
            for &candidate_id in &start_events[window_idx] {
                if !active_listed[candidate_id] {
                    active_ids.push(candidate_id);
                    active_listed[candidate_id] = true;
                }
                active_counts[candidate_id] = active_counts[candidate_id]
                    .checked_add(1)
                    .expect("window activity overflow");
            }

            present_ids.clear();
            let mut write_idx = 0usize;
            for read_idx in 0..active_ids.len() {
                let candidate_id = active_ids[read_idx];
                if active_counts[candidate_id] == 0 {
                    active_listed[candidate_id] = false;
                    continue;
                }
                active_ids[write_idx] = candidate_id;
                write_idx += 1;
                present_ids.push(candidate_id);
            }
            active_ids.truncate(write_idx);
            if present_ids.is_empty() {
                continue;
            }

            present_ids.sort_unstable();
            for (index, &left_id) in present_ids.iter().enumerate() {
                importance_counts[left_id] += 1;
                let row_offset = left_id * candidate_count;
                for &right_id in &present_ids[index + 1..] {
                    let pair_key = row_offset + right_id;
                    pair_counts[pair_key] += 1;
                }
            }
        }
    }

    Ok((shortlisted_candidates, importance_counts, pair_counts))
}

/// Threshold the raw counts and flatten the pair matrix into sorted
/// `(left_id, right_id, count)` items.
pub(crate) fn compact_window_items(
    candidate_names: Vec<String>,
    importance_counts: Vec<usize>,
    pair_counts: Vec<u32>,
    threshold: usize,
) -> CompactWindowItems {
    if candidate_names.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }

    let candidate_count = candidate_names.len();
    let mut included_candidate_ids = Vec::new();
    let mut importance_items = Vec::new();
    for (candidate_id, count) in importance_counts.into_iter().enumerate() {
        if count < threshold {
            continue;
        }
        included_candidate_ids.push(candidate_id);
        importance_items.push((candidate_id, count));
    }
    if importance_items.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }

    let included_count = included_candidate_ids.len();
    let max_pair_items = included_count.saturating_mul(included_count.saturating_sub(1)) / 2;
    let mut pair_items: Vec<(usize, usize, usize)> = Vec::with_capacity(max_pair_items);
    for (index, &left_id) in included_candidate_ids.iter().enumerate() {
        let row_offset = left_id * candidate_count;
        for &right_id in &included_candidate_ids[index + 1..] {
            let count = pair_counts[row_offset + right_id] as usize;
            if count > 0 {
                pair_items.push((left_id, right_id, count));
            }
        }
    }
    pair_items.sort_unstable_by(|left, right| {
        right
            .2
            .cmp(&left.2)
            .then_with(|| left.0.cmp(&right.0))
            .then_with(|| left.1.cmp(&right.1))
    });

    (candidate_names, importance_items, pair_items)
}

fn collect_ascii_window_events(
    chapter: &str,
    shortlisted_candidates: &[String],
    candidate_char_lens: &[usize],
    window_size: usize,
    chapter_window_starts: &[usize],
    start_events: &mut [Vec<usize>],
    end_events: &mut [Vec<usize>],
) {
    for (candidate_id, candidate) in shortlisted_candidates.iter().enumerate() {
        if candidate.is_empty() {
            continue;
        }
        let mut search_start = 0usize;
        while search_start <= chapter.len() {
            let Some(relative_start) = chapter[search_start..].find(candidate.as_str()) else {
                break;
            };
            let start_char = search_start + relative_start;
            let end_char = start_char + candidate_char_lens[candidate_id];
            let min_window_start = end_char.saturating_sub(window_size);
            let max_window_start = start_char;
            let first_window_idx = chapter_window_starts
                .partition_point(|&window_start| window_start < min_window_start);
            let end_window_idx = chapter_window_starts
                .partition_point(|&window_start| window_start <= max_window_start);
            if first_window_idx < end_window_idx {
                start_events[first_window_idx].push(candidate_id);
                end_events[end_window_idx].push(candidate_id);
            }
            search_start = start_char.saturating_add(1);
        }
    }
}

fn prepare_event_buckets(buckets: &mut Vec<Vec<usize>>, required_len: usize) {
    if buckets.len() < required_len {
        buckets.resize_with(required_len, Vec::new);
    }
    for bucket in buckets.iter_mut().take(required_len) {
        bucket.clear();
    }
}

fn window_starts_into(
    char_count: usize,
    window_size: usize,
    window_step: usize,
    starts: &mut Vec<usize>,
) {
    starts.clear();
    if char_count == 0 {
        return;
    }
    if char_count <= window_size {
        starts.push(0);
        return;
    }

    let last_start = char_count - window_size;
    let mut start = 0usize;
    while start < last_start {
        starts.push(start);
        match start.checked_add(window_step) {
            Some(next_start) => start = next_start,
            None => break,
        }
    }
    if starts.last().copied() != Some(last_start) {
        starts.push(last_start);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn collect_char_starts(text: &str) -> Vec<usize> {
        let mut char_starts = Vec::new();
        collect_char_starts_into(text, &mut char_starts);
        char_starts
    }

    fn window_starts(char_count: usize, window_size: usize, window_step: usize) -> Vec<usize> {
        let mut starts = Vec::new();
        window_starts_into(char_count, window_size, window_step, &mut starts);
        starts
    }

    fn naive_summarize_window_counts(
        chapters: &[String],
        shortlisted_candidates: &[String],
        window_size: usize,
        window_step: usize,
    ) -> Result<WindowCounts, String> {
        let mut shortlisted_candidates: Vec<String> = shortlisted_candidates.to_vec();
        shortlisted_candidates.sort_unstable();
        shortlisted_candidates.dedup();
        let candidate_count = shortlisted_candidates.len();
        let pair_matrix_len = candidate_count
            .checked_mul(candidate_count)
            .ok_or_else(|| "candidate matrix too large".to_string())?;
        let automaton = AhoCorasick::new(&shortlisted_candidates).map_err(|err| err.to_string())?;
        let mut importance_counts = vec![0usize; candidate_count];
        let mut pair_counts = vec![0u32; pair_matrix_len];
        let mut seen_generations = vec![0u64; candidate_count];
        let mut window_generation = 0u64;
        let mut present_ids = Vec::new();

        for chapter in chapters {
            let chapter: &str = chapter.as_str();
            let char_starts = collect_char_starts(chapter);
            let char_count = char_starts.len().saturating_sub(1);
            if char_count == 0 {
                continue;
            }
            for start_char in window_starts(char_count, window_size, window_step) {
                window_generation += 1;
                present_ids.clear();
                let end_char = (start_char + window_size).min(char_count);
                let start_byte = char_starts[start_char];
                let end_byte = char_starts[end_char];
                let window_text = &chapter[start_byte..end_byte];

                for mat in automaton.find_overlapping_iter(window_text) {
                    let candidate_id = mat.pattern().as_usize();
                    if seen_generations[candidate_id] == window_generation {
                        continue;
                    }
                    seen_generations[candidate_id] = window_generation;
                    present_ids.push(candidate_id);
                }
                if present_ids.is_empty() {
                    continue;
                }
                present_ids.sort_unstable();
                for (index, &left_id) in present_ids.iter().enumerate() {
                    importance_counts[left_id] += 1;
                    let row_offset = left_id * candidate_count;
                    for &right_id in &present_ids[index + 1..] {
                        pair_counts[row_offset + right_id] += 1;
                    }
                }
            }
        }

        Ok((shortlisted_candidates, importance_counts, pair_counts))
    }

    #[test]
    fn event_diff_summary_matches_naive_window_rescan() {
        let chapters =
            vec!["顾衡在云港司守夜。顾衡与林秋又回到云港司，云港司里提起旧案。".to_owned()];
        let shortlisted_candidates = vec![
            "顾衡".to_owned(),
            "云港".to_owned(),
            "云港司".to_owned(),
            "林秋".to_owned(),
            "旧案".to_owned(),
        ];

        let naive = naive_summarize_window_counts(&chapters, &shortlisted_candidates, 12, 6)
            .expect("naive summary should succeed");
        let fast = summarize_window_counts(chapters, shortlisted_candidates, 12, 6)
            .expect("fast summary should succeed");

        assert_eq!(naive.0, fast.0);
        assert_eq!(naive.1, fast.1);
        assert_eq!(naive.2, fast.2);
        assert!(fast.1.iter().any(|count| *count > 0));
        assert!(fast.2.iter().any(|count| *count > 0));
    }
}
