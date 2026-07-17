//! Embedded zh lexicon tables and character/shape predicates shared by the
//! bootstrap candidate pipeline.

use rustc_hash::FxHashSet;
use std::sync::OnceLock;

pub(crate) const ZH_FRAGMENT_MAX_TOKEN_CHARS: usize = 3;

const ZH_SINGLE_SURNAMES: &str =
    include_str!("../../../../app/core/indexing/data/zh_single_surnames.txt");
const ZH_COMPOUND_SURNAMES: &str =
    include_str!("../../../../app/core/indexing/data/zh_compound_surnames.txt");
const ZH_NAME_TRAILING_NOISE_CHARS: &str =
    include_str!("../../../../app/core/indexing/data/zh_name_trailing_noise_chars.txt");
const ZH_TRANSLIT_CHARS: &str =
    include_str!("../../../../app/core/indexing/data/zh_translit_chars.txt");
const ZH_NAME_SUFFIX_TITLES: &str =
    include_str!("../../../../app/core/indexing/data/zh_name_suffix_titles.txt");

fn char_set(raw: &str, cell: &'static OnceLock<FxHashSet<char>>) -> &'static FxHashSet<char> {
    cell.get_or_init(|| raw.chars().filter(|ch| !ch.is_whitespace()).collect())
}

fn zh_single_surname_chars() -> &'static FxHashSet<char> {
    static CHARS: OnceLock<FxHashSet<char>> = OnceLock::new();
    char_set(ZH_SINGLE_SURNAMES, &CHARS)
}

fn zh_name_trailing_noise_chars() -> &'static FxHashSet<char> {
    static CHARS: OnceLock<FxHashSet<char>> = OnceLock::new();
    char_set(ZH_NAME_TRAILING_NOISE_CHARS, &CHARS)
}

fn zh_translit_chars() -> &'static FxHashSet<char> {
    static CHARS: OnceLock<FxHashSet<char>> = OnceLock::new();
    char_set(ZH_TRANSLIT_CHARS, &CHARS)
}

fn zh_compound_surnames() -> &'static FxHashSet<&'static str> {
    static COMPOUND_SURNAMES: OnceLock<FxHashSet<&'static str>> = OnceLock::new();
    COMPOUND_SURNAMES.get_or_init(|| {
        ZH_COMPOUND_SURNAMES
            .lines()
            .map(str::trim)
            .filter(|surname| !surname.is_empty())
            .collect()
    })
}

fn zh_name_suffix_titles() -> &'static FxHashSet<&'static str> {
    static SUFFIX_TITLES: OnceLock<FxHashSet<&'static str>> = OnceLock::new();
    SUFFIX_TITLES.get_or_init(|| {
        ZH_NAME_SUFFIX_TITLES
            .lines()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .collect()
    })
}

pub(crate) fn is_cjk_name_char(ch: char) -> bool {
    matches!(
        ch as u32,
        0x3400..=0x4DBF
            | 0x4E00..=0x9FFF
            | 0xF900..=0xFAFF
            | 0x20000..=0x2A6DF
            | 0x2A700..=0x2B73F
            | 0x2B740..=0x2B81F
            | 0x2B820..=0x2CEAF
            | 0x2CEB0..=0x2EBEF
            | 0x2F800..=0x2FA1F
    )
}

pub(crate) fn is_cjk_token(value: &str) -> bool {
    !value.is_empty() && value.chars().all(is_cjk_name_char)
}

pub(crate) fn is_zh_single_surname_char(ch: char) -> bool {
    zh_single_surname_chars().contains(&ch)
}

pub(crate) fn is_zh_single_surname(value: &str) -> bool {
    let mut chars = value.chars();
    matches!(
        chars.next(),
        Some(ch) if chars.next().is_none() && is_zh_single_surname_char(ch)
    )
}

pub(crate) fn is_zh_compound_surname(value: &str) -> bool {
    zh_compound_surnames().contains(value)
}

pub(crate) fn is_zh_name_trailing_block_char(ch: char) -> bool {
    zh_name_trailing_noise_chars().contains(&ch)
}

pub(crate) fn looks_like_zh_person_name(value: &str) -> bool {
    if !is_cjk_token(value) {
        return false;
    }

    match value.chars().count() {
        2 => prefix_chars(value, 1).is_some_and(is_zh_single_surname),
        3 => {
            prefix_chars(value, 1).is_some_and(is_zh_single_surname)
                || prefix_chars(value, 2).is_some_and(is_zh_compound_surname)
        }
        4 => prefix_chars(value, 2).is_some_and(is_zh_compound_surname),
        _ => false,
    }
}

/// "顾慎为看" -> Some("顾慎为"): a person-shaped root plus one trailing noise char.
pub(crate) fn strip_zh_person_name_trailing_noise(value: &str) -> Option<&str> {
    if !is_cjk_token(value) || value.chars().count() < 3 {
        return None;
    }

    let (last_byte_idx, last_char) = value.char_indices().last()?;
    if !is_zh_name_trailing_block_char(last_char) {
        return None;
    }

    let canonical = &value[..last_byte_idx];
    looks_like_zh_person_name(canonical).then_some(canonical)
}

pub(crate) fn looks_like_zh_translit_fragment(value: &str) -> bool {
    !value.is_empty()
        && is_cjk_token(value)
        && value.chars().all(|ch| zh_translit_chars().contains(&ch))
}

pub(crate) fn is_short_translit_fragment(value: &str) -> bool {
    value.chars().count() <= ZH_FRAGMENT_MAX_TOKEN_CHARS && looks_like_zh_translit_fragment(value)
}

pub(crate) fn is_zh_name_suffix_title(value: &str) -> bool {
    zh_name_suffix_titles().contains(value)
}

pub(crate) fn prefix_chars(value: &str, count: usize) -> Option<&str> {
    if count == 0 {
        return Some("");
    }
    let mut seen = 0usize;
    for (byte_idx, ch) in value.char_indices() {
        seen += 1;
        if seen == count {
            return Some(&value[..byte_idx + ch.len_utf8()]);
        }
    }
    None
}

pub(crate) fn suffix_after_removing_prefix_chars(value: &str, count: usize) -> Option<&str> {
    if count == 0 {
        return Some(value);
    }
    let mut seen = 0usize;
    for (byte_idx, ch) in value.char_indices() {
        seen += 1;
        if seen == count {
            return Some(&value[byte_idx + ch.len_utf8()..]);
        }
    }
    None
}

pub(crate) fn has_min_chars(value: &str, min_chars: usize) -> bool {
    if min_chars <= 1 {
        return !value.is_empty();
    }
    value.chars().nth(min_chars - 1).is_some()
}

pub(crate) fn all_same_chars(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return true;
    };
    chars.all(|ch| ch == first)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strip_zh_person_name_trailing_noise_keeps_person_roots_only() {
        assert_eq!(strip_zh_person_name_trailing_noise("罗碧不"), Some("罗碧"));
        assert_eq!(
            strip_zh_person_name_trailing_noise("顾慎为看"),
            Some("顾慎为")
        );
        assert_eq!(strip_zh_person_name_trailing_noise("炙皇星看"), None);
        assert_eq!(strip_zh_person_name_trailing_noise("战士们"), None);
    }
}
