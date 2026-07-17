//! Token normalization for zh candidate counting: trimming, NFKC folding,
//! case-fold classification, and variant-character canonicalization.

use rustc_hash::FxHashMap;
use std::borrow::Cow;
use std::sync::OnceLock;
use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;

const ZH_VARIANT_CHAR_LINES: &str =
    include_str!("../../../../app/core/indexing/data/zh_variant_chars.tsv");

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum MatchNormalization {
    None,
    AsciiLower,
    UnicodeCaseFold,
}

pub(crate) fn classify_match_normalization(value: &str) -> MatchNormalization {
    let mut saw_ascii_upper = false;
    for ch in value.chars() {
        if ch.is_ascii_uppercase() {
            saw_ascii_upper = true;
            continue;
        }
        if !ch.is_ascii() && ch.is_alphabetic() && !is_simple_nfkc_cjk(ch) {
            return MatchNormalization::UnicodeCaseFold;
        }
    }
    if saw_ascii_upper {
        MatchNormalization::AsciiLower
    } else {
        MatchNormalization::None
    }
}

pub(crate) fn normalize_for_matching(value: &str) -> Cow<'_, str> {
    let folded: String = value.case_fold().collect();
    if folded == value {
        Cow::Borrowed(value)
    } else {
        Cow::Owned(folded)
    }
}

pub(crate) fn normalize_token(token: &str) -> Cow<'_, str> {
    let trimmed = trim_token(token);
    if trimmed.is_empty() {
        return Cow::Borrowed(trimmed);
    }
    if is_simple_nfkc_token(trimmed) {
        return Cow::Borrowed(trimmed);
    }
    let normalized: String = trimmed.nfkc().collect();
    if normalized == trimmed {
        Cow::Borrowed(trimmed)
    } else {
        Cow::Owned(trim_owned_token(normalized))
    }
}

fn is_simple_nfkc_token(value: &str) -> bool {
    value
        .chars()
        .all(|ch| ch.is_ascii() || is_simple_nfkc_cjk(ch))
}

fn is_simple_nfkc_cjk(ch: char) -> bool {
    matches!(ch as u32, 0x3400..=0x4DBF | 0x4E00..=0x9FFF | 0xF900..=0xFAFF)
}

fn trim_owned_token(value: String) -> String {
    let trimmed = trim_token(&value);
    if trimmed.len() == value.len() {
        value
    } else {
        trimmed.to_owned()
    }
}

fn trim_token(value: &str) -> &str {
    value.trim_matches(is_trim_char)
}

fn is_trim_char(ch: char) -> bool {
    matches!(
        ch,
        ' ' | '\t'
            | '\r'
            | '\n'
            | '.'
            | ','
            | '!'
            | '?'
            | ';'
            | ':'
            | '"'
            | '\''
            | '('
            | ')'
            | '['
            | ']'
            | '{'
            | '}'
            | '<'
            | '>'
            | '，'
            | '。'
            | '！'
            | '？'
            | '；'
            | '：'
            | '、'
            | '“'
            | '”'
            | '‘'
            | '’'
            | '（'
            | '）'
            | '【'
            | '】'
            | '《'
            | '》'
            | '…'
            | '·'
            | '-'
            | '—'
    )
}

fn zh_variant_char_map() -> &'static FxHashMap<char, char> {
    static VARIANT_CHAR_MAP: OnceLock<FxHashMap<char, char>> = OnceLock::new();
    VARIANT_CHAR_MAP.get_or_init(|| {
        ZH_VARIANT_CHAR_LINES
            .lines()
            .filter_map(|line| {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    return None;
                }
                let mut parts = trimmed.split('\t');
                let src = parts.next()?.trim();
                let dst = parts.next()?.trim();
                if parts.next().is_some() || src.chars().count() != 1 || dst.chars().count() != 1 {
                    return None;
                }
                Some((src.chars().next()?, dst.chars().next()?))
            })
            .collect()
    })
}

pub(crate) fn normalize_zh_variant_chars(value: &str) -> Cow<'_, str> {
    if value.is_empty() {
        return Cow::Borrowed(value);
    }

    let variant_map = zh_variant_char_map();
    if variant_map.is_empty() {
        return Cow::Borrowed(value);
    }

    let mut changed = false;
    let mut normalized = String::with_capacity(value.len());
    for ch in value.chars() {
        let mapped = variant_map.get(&ch).copied().unwrap_or(ch);
        changed |= mapped != ch;
        normalized.push(mapped);
    }

    if changed {
        Cow::Owned(normalized)
    } else {
        Cow::Borrowed(value)
    }
}

pub(crate) fn normalize_zh_chapter_strings<T>(chapters: impl IntoIterator<Item = T>) -> Vec<String>
where
    T: AsRef<str>,
{
    chapters
        .into_iter()
        .map(|chapter| normalize_zh_variant_chars(chapter.as_ref()).into_owned())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_token_keeps_fast_path_and_compatibility_path_equivalent() {
        assert_eq!(normalize_token("顾衡").as_ref(), "顾衡");
        assert_eq!(normalize_token("，顾衡。").as_ref(), "顾衡");
        assert_eq!(normalize_token("ＡＢＣ").as_ref(), "ABC");
        assert_eq!(normalize_token("﹙顾衡﹚").as_ref(), "顾衡");
        assert_eq!(normalize_token("Ⅳ").as_ref(), "IV");
    }

    #[test]
    fn classify_match_normalization_uses_ascii_and_unicode_paths() {
        assert_eq!(
            classify_match_normalization("顾衡"),
            MatchNormalization::None
        );
        assert_eq!(
            classify_match_normalization("ABC"),
            MatchNormalization::AsciiLower
        );
        assert_eq!(
            classify_match_normalization("ÄBC"),
            MatchNormalization::UnicodeCaseFold
        );
    }
}
