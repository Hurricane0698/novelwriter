//! Pure-Rust zh bootstrap text helpers (candidate counting, window summaries,
//! block refinement). No PyO3 types: the Python boundary stays in `lib.rs`.

pub(crate) mod blocks;
pub(crate) mod candidates;
pub(crate) mod lexicon;
pub(crate) mod normalize;
pub(crate) mod windows;

pub(crate) type CandidateCount = u32;

/// Char-start byte offsets for `text`, plus a trailing `text.len()` sentinel.
pub(crate) fn collect_char_starts_into(text: &str, char_starts: &mut Vec<usize>) {
    char_starts.clear();
    char_starts.extend(text.char_indices().map(|(idx, _)| idx));
    char_starts.push(text.len());
}
