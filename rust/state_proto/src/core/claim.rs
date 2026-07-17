use super::mention::{AliasMatch, SegmentAliasMatches};
use super::segment::{detect_script_mode, is_cjk, pack_claim_id};
use super::*;
use std::sync::LazyLock;

static ZH_LOCATION_VALUE_BODY_RE: LazyLock<String> = LazyLock::new(build_zh_location_value_body);
static ZH_AFFILIATION_VALUE_BODY_RE: LazyLock<String> =
    LazyLock::new(build_zh_affiliation_value_body);
static EN_STRUCTURED_VALUE_BODY_RE: LazyLock<String> =
    LazyLock::new(build_en_structured_value_body);
static ZH_ROLE_RE: LazyLock<String> = LazyLock::new(|| join_regex_alternation(ROLE_KEYWORDS_ZH));
static EN_ROLE_RE: LazyLock<String> = LazyLock::new(|| join_regex_alternation(ROLE_KEYWORDS_EN));
static DETERMINER_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:这|那|某|一)(?:座|间|条|处|个|所|片|家)").expect("determiner regex")
});

const CLAIM_SEARCH_WINDOW_MAX_CHARS: usize = 192;

#[derive(Debug)]
struct LifeStatePattern {
    state: &'static str,
    confidence: f64,
    regex: Regex,
}

#[derive(Debug)]
pub(crate) struct AliasPatternSet {
    zh_location_contrast: Regex,
    zh_location: Regex,
    en_location_asserted: Regex,
    en_location_motion: Regex,
    zh_affiliation_membership: Regex,
    zh_affiliation_role: Regex,
    en_affiliation: Regex,
    zh_role: Regex,
    en_role: Regex,
    zh_life_state_patterns: Vec<LifeStatePattern>,
    en_life_state_patterns: Vec<LifeStatePattern>,
    zh_owner: Regex,
    en_owner: Regex,
}

impl AliasPatternSet {
    pub(crate) fn build(alias: &str) -> Result<Self, PayloadError> {
        let escaped_alias = regex::escape(alias);
        let zh_location_body = ZH_LOCATION_VALUE_BODY_RE.as_str();
        let zh_affiliation_body = ZH_AFFILIATION_VALUE_BODY_RE.as_str();
        let en_structured_value_body = EN_STRUCTURED_VALUE_BODY_RE.as_str();

        let zh_life_state_patterns = build_life_state_patterns(
            &escaped_alias,
            true,
            &[
                ("dead", LIFE_STATE_ZH_DEAD, 1.0),
                ("missing", LIFE_STATE_ZH_MISSING, 1.0),
                ("incapacitated", LIFE_STATE_ZH_INCAPACITATED, 0.9),
                ("alive", LIFE_STATE_ZH_ALIVE, 1.0),
            ],
        )?;
        let en_life_state_patterns = build_life_state_patterns(
            &escaped_alias,
            false,
            &[
                ("dead", LIFE_STATE_EN_DEAD, 1.0),
                ("missing", LIFE_STATE_EN_MISSING, 1.0),
                ("incapacitated", LIFE_STATE_EN_INCAPACITATED, 0.9),
                ("alive", LIFE_STATE_EN_ALIVE, 1.0),
            ],
        )?;

        Ok(Self {
            zh_location_contrast: compile_regex(&format!(
                r"\A{alias}(?:不在|并非在|不再在|未在)(?P<old>{body})(?:[，,；;])?(?:却|但|而)?(?:又)?(?:在|于)(?P<new>{body})",
                alias = escaped_alias,
                body = zh_location_body,
            ))?,
            zh_location: compile_regex(&format!(
                r"\A{alias}(?:此时|现在|如今|这时|当下)?(?:正|仍|还|已|曾|曾经|可能|也许|或许)?(?:在|于|来到|回到|留在|待在|身处|位于|赶到|住在)(?P<value>{body})",
                alias = escaped_alias,
                body = zh_location_body,
            ))?,
            en_location_asserted: compile_ci_regex(&format!(
                r"\A{alias}\s+(?:is|was|remains|stays|stayed)\s+(?:in|at|inside)\s+(?P<value>{body})",
                alias = escaped_alias,
                body = en_structured_value_body,
            ))?,
            en_location_motion: compile_ci_regex(&format!(
                r"\A{alias}\s+(?:arrived|returned|came|went|walked|moved)\s+(?:to|into)\s+(?P<value>{body})",
                alias = escaped_alias,
                body = en_structured_value_body,
            ))?,
            zh_affiliation_membership: compile_regex(&format!(
                r"\A{alias}(?:加入|投靠|归入|归属(?:于)?|隶属(?:于)?)(?P<value>{body})",
                alias = escaped_alias,
                body = zh_affiliation_body,
            ))?,
            zh_affiliation_role: compile_regex(&format!(
                r"\A{alias}(?:是|作为)(?P<value>{body})(?:弟子|成员|门人|客卿)",
                alias = escaped_alias,
                body = zh_affiliation_body,
            ))?,
            en_affiliation: compile_ci_regex(&format!(
                r"\A{alias}\s+(?:joined|belongs to|is with)\s+(?P<value>{body})",
                alias = escaped_alias,
                body = en_structured_value_body,
            ))?,
            zh_role: compile_regex(&format!(
                r"\A{alias}(?:如今|现在|现为|仍是|还是|是|成为|担任|出任|任)(?P<value>{role_re})",
                alias = escaped_alias,
                role_re = ZH_ROLE_RE.as_str(),
            ))?,
            en_role: compile_ci_regex(&format!(
                r"\A{alias}\s+(?:is|became|serves as|served as)\s+(?P<value>{role_re})",
                alias = escaped_alias,
                role_re = EN_ROLE_RE.as_str(),
            ))?,
            zh_life_state_patterns,
            en_life_state_patterns,
            zh_owner: compile_regex(&format!(
                r"\A{alias}(?:如今|现在)?(?:在|落在|回到|归于|归属(?:于)?|归)(?P<value>[^，。！？；：、“”‘’（）()\n]{{2,12}})(?:手中|名下|所有)",
                alias = escaped_alias,
            ))?,
            en_owner: compile_ci_regex(&format!(
                r"\A{alias}\s+(?:belongs to|is with|rests with)\s+(?P<value>{body})",
                alias = escaped_alias,
                body = en_structured_value_body,
            ))?,
        })
    }
}

#[derive(Debug, Clone)]
struct ClaimCandidate {
    slot: &'static str,
    value_signature: String,
    anchor_offset: usize,
    confidence: f64,
    cue_bitmap: i64,
    change_salience: f64,
}

pub(crate) fn build_claim_atoms(
    chapter_id: i64,
    segments: &[SegmentData],
    indexed: &IndexedText,
    context: &BuildContext,
    grouped_matches: &SegmentAliasMatches,
) -> Result<Vec<ClaimData>, PayloadError> {
    if segments.is_empty() || grouped_matches.is_empty() {
        return Ok(Vec::new());
    }
    let mut deduped: HashMap<(String, String, String, i64), ClaimData> = HashMap::new();
    for segment in segments {
        let Some(target_matches) = grouped_matches.get(&segment.segment_id) else {
            continue;
        };
        let segment_indexed = IndexedTextSlice::new(
            indexed,
            segment.start_pos as usize,
            segment.end_pos as usize,
        );
        let script_mode = detect_script_mode(segment_indexed.chars);
        for (target_id, matches) in target_matches {
            let Some(target) = context.targets_by_id.get(target_id) else {
                continue;
            };
            let claims_for_target =
                extract_claims_for_target(target, &segment_indexed, matches, context, script_mode)?;
            for candidate in claims_for_target {
                let dedupe_key = (
                    target.id.clone(),
                    candidate.slot.to_owned(),
                    candidate.value_signature.clone(),
                    segment.segment_id,
                );
                let claim = ClaimData {
                    claim_id: 0,
                    target_id: target.id.clone(),
                    slot: candidate.slot.to_owned(),
                    value_signature: candidate.value_signature,
                    segment_id: segment.segment_id,
                    chapter_number: segment.chapter_number,
                    anchor_offset: candidate.anchor_offset as i64,
                    confidence: candidate.confidence,
                    cue_bitmap: candidate.cue_bitmap,
                    change_salience: candidate.change_salience,
                };
                match deduped.entry(dedupe_key) {
                    std::collections::hash_map::Entry::Vacant(entry) => {
                        entry.insert(claim);
                    }
                    std::collections::hash_map::Entry::Occupied(mut entry) => {
                        let merged = merge_claims(entry.get(), &claim);
                        entry.insert(merged);
                    }
                }
            }
        }
    }

    let mut ordered: Vec<ClaimData> = deduped.into_values().collect();
    ordered.sort_by(|left, right| {
        (
            left.chapter_number,
            left.segment_id,
            left.anchor_offset,
            left.slot.as_str(),
            left.value_signature.as_str(),
        )
            .cmp(&(
                right.chapter_number,
                right.segment_id,
                right.anchor_offset,
                right.slot.as_str(),
                right.value_signature.as_str(),
            ))
    });
    for (index, claim) in ordered.iter_mut().enumerate() {
        claim.claim_id = pack_claim_id(chapter_id, (index + 1) as i64);
        claim.confidence = round_places(claim.confidence, 4);
        claim.change_salience = round_places(claim.change_salience, 4);
    }
    Ok(ordered)
}

fn extract_claims_for_target(
    target: &RequestTarget,
    segment_text: &IndexedTextSlice<'_>,
    matches: &[AliasMatch],
    context: &BuildContext,
    script_mode: &str,
) -> Result<Vec<ClaimCandidate>, PayloadError> {
    let unique_matches = dedupe_alias_matches(matches);
    let mut claims = Vec::new();
    for matched in unique_matches {
        let search_window = ClaimSearchWindow::new(segment_text, &matched, script_mode);
        let patterns = context.get_alias_patterns(&matched.alias)?;
        if target.kind == TARGET_KIND_ARTIFACT {
            claims.extend(extract_owner_claims(
                &search_window,
                &matched,
                patterns.as_ref(),
                &context.canonical_name_by_surface,
                script_mode,
            ));
            continue;
        }
        claims.extend(extract_location_claims(
            &search_window,
            &matched,
            patterns.as_ref(),
            &context.canonical_name_by_surface,
            script_mode,
        ));
        claims.extend(extract_affiliation_claims(
            &search_window,
            &matched,
            patterns.as_ref(),
            &context.canonical_name_by_surface,
            script_mode,
        ));
        claims.extend(extract_role_claims(
            &search_window,
            &matched,
            patterns.as_ref(),
            script_mode,
        ));
        claims.extend(extract_life_state_claims(
            &search_window,
            &matched,
            patterns.as_ref(),
            script_mode,
        ));
    }
    Ok(claims)
}

struct ClaimSearchWindow<'a> {
    segment: &'a IndexedTextSlice<'a>,
    text: &'a str,
    base_byte: usize,
}

impl<'a> ClaimSearchWindow<'a> {
    fn new(segment: &'a IndexedTextSlice<'a>, matched: &AliasMatch, script_mode: &str) -> Self {
        let start_char = matched.start;
        let end_char = claim_window_end_char(segment, start_char, script_mode);
        let start_byte =
            segment.parent.char_to_byte(segment.start_char + start_char) - segment.start_byte;
        let end_byte =
            segment.parent.char_to_byte(segment.start_char + end_char) - segment.start_byte;
        Self {
            segment,
            text: &segment.text[start_byte..end_byte],
            base_byte: start_byte,
        }
    }

    fn byte_to_segment_char(&self, byte_idx: usize) -> usize {
        self.segment.byte_to_char(self.base_byte + byte_idx)
    }
}

fn claim_window_end_char(
    segment: &IndexedTextSlice<'_>,
    start_char: usize,
    script_mode: &str,
) -> usize {
    let limit = usize::min(
        start_char + CLAIM_SEARCH_WINDOW_MAX_CHARS,
        segment.char_len(),
    );
    let terminators = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        CJK_SENTENCE_TERMINATORS
    } else {
        NON_CJK_SENTENCE_TERMINATORS
    };
    let mut cursor = start_char;
    while cursor < limit {
        let ch = segment.chars[cursor];
        cursor += 1;
        if ch == '\n' || terminators.contains(&ch) {
            while cursor < limit && SENTENCE_CLOSERS.contains(&segment.chars[cursor]) {
                cursor += 1;
            }
            return cursor;
        }
    }
    limit
}

/// Shared tail of every value-bearing claim extraction: normalize the captured
/// value, derive the cue bitmap from the local context, then push a candidate.
#[allow(clippy::too_many_arguments)]
fn push_normalized_claim(
    claims: &mut Vec<ClaimCandidate>,
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    value_match: regex::Match<'_>,
    slot: &'static str,
    canonical_name_by_surface: &HashMap<String, String>,
    confidence: f64,
    change_salience: f64,
) {
    let Some(value) =
        normalize_value_signature(value_match.as_str(), slot, canonical_name_by_surface)
    else {
        return;
    };
    let cue_bitmap = detect_cue_bitmap(
        search_window.segment,
        matched.start,
        search_window.byte_to_segment_char(value_match.end()),
    );
    claims.push(ClaimCandidate {
        slot,
        value_signature: value,
        anchor_offset: search_window.byte_to_segment_char(value_match.start()),
        confidence,
        cue_bitmap,
        change_salience,
    });
}

fn extract_location_claims(
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    patterns: &AliasPatternSet,
    canonical_name_by_surface: &HashMap<String, String>,
    script_mode: &str,
) -> Vec<ClaimCandidate> {
    let mut claims = Vec::new();
    let text = search_window.text;
    if script_mode == SCRIPT_MODE_CJK_HEAVY {
        if let Some(captures) = patterns.zh_location_contrast.captures(text) {
            if let Some(old_match) = captures.name("old") {
                if let Some(value) = normalize_value_signature(
                    old_match.as_str(),
                    SLOT_ENTITY_CURRENT_LOCATION,
                    canonical_name_by_surface,
                ) {
                    claims.push(ClaimCandidate {
                        slot: SLOT_ENTITY_CURRENT_LOCATION,
                        value_signature: value,
                        anchor_offset: matched.start,
                        confidence: 0.9,
                        cue_bitmap: CUE_NEGATED,
                        change_salience: 1.0,
                    });
                }
            }
            if let Some(new_match) = captures.name("new") {
                if let Some(value) = normalize_value_signature(
                    new_match.as_str(),
                    SLOT_ENTITY_CURRENT_LOCATION,
                    canonical_name_by_surface,
                ) {
                    claims.push(ClaimCandidate {
                        slot: SLOT_ENTITY_CURRENT_LOCATION,
                        value_signature: value,
                        anchor_offset: search_window.byte_to_segment_char(new_match.start()),
                        confidence: 0.9,
                        cue_bitmap: CUE_ASSERTED,
                        change_salience: 1.1,
                    });
                }
            }
        }

        if let Some(value_match) = patterns
            .zh_location
            .captures(text)
            .and_then(|captures| captures.name("value"))
        {
            push_normalized_claim(
                &mut claims,
                search_window,
                matched,
                value_match,
                SLOT_ENTITY_CURRENT_LOCATION,
                canonical_name_by_surface,
                0.9,
                1.1,
            );
        }
    } else {
        for regex in [&patterns.en_location_asserted, &patterns.en_location_motion] {
            let Some(value_match) = regex
                .captures(text)
                .and_then(|captures| captures.name("value"))
            else {
                continue;
            };
            push_normalized_claim(
                &mut claims,
                search_window,
                matched,
                value_match,
                SLOT_ENTITY_CURRENT_LOCATION,
                canonical_name_by_surface,
                0.9,
                1.1,
            );
        }
    }
    claims
}

fn extract_affiliation_claims(
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    patterns: &AliasPatternSet,
    canonical_name_by_surface: &HashMap<String, String>,
    script_mode: &str,
) -> Vec<ClaimCandidate> {
    let mut claims = Vec::new();
    let text = search_window.text;
    let regexes: &[&Regex] = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        &[
            &patterns.zh_affiliation_membership,
            &patterns.zh_affiliation_role,
        ]
    } else {
        &[&patterns.en_affiliation]
    };
    for regex in regexes {
        let Some(value_match) = regex
            .captures(text)
            .and_then(|captures| captures.name("value"))
        else {
            continue;
        };
        push_normalized_claim(
            &mut claims,
            search_window,
            matched,
            value_match,
            SLOT_ENTITY_CURRENT_AFFILIATION,
            canonical_name_by_surface,
            0.85,
            1.0,
        );
    }
    claims
}

fn extract_role_claims(
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    patterns: &AliasPatternSet,
    script_mode: &str,
) -> Vec<ClaimCandidate> {
    let mut claims = Vec::new();
    let segment_text = search_window.segment;
    let regex = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        &patterns.zh_role
    } else {
        &patterns.en_role
    };
    if let Some(captures) = regex.captures(search_window.text) {
        if let Some(value_match) = captures.name("value") {
            let cue_bitmap = detect_cue_bitmap(
                segment_text,
                matched.start,
                search_window.byte_to_segment_char(value_match.end()),
            );
            claims.push(ClaimCandidate {
                slot: SLOT_ENTITY_CURRENT_ROLE,
                value_signature: if script_mode == SCRIPT_MODE_CJK_HEAVY {
                    value_match.as_str().to_owned()
                } else {
                    value_match.as_str().to_ascii_lowercase()
                },
                anchor_offset: search_window.byte_to_segment_char(value_match.start()),
                confidence: 0.9,
                cue_bitmap,
                change_salience: 1.0,
            });
        }
    }
    claims
}

fn extract_life_state_claims(
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    patterns: &AliasPatternSet,
    script_mode: &str,
) -> Vec<ClaimCandidate> {
    let mut claims = Vec::new();
    let segment_text = search_window.segment;
    let life_state_patterns = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        &patterns.zh_life_state_patterns
    } else {
        &patterns.en_life_state_patterns
    };
    for pattern in life_state_patterns {
        let Some(found) = pattern.regex.find(search_window.text) else {
            continue;
        };
        let cue_bitmap = detect_cue_bitmap(
            segment_text,
            matched.start,
            search_window.byte_to_segment_char(found.end()),
        );
        let anchor_offset = search_window.byte_to_segment_char(found.start());
        claims.push(ClaimCandidate {
            slot: SLOT_ENTITY_LIFE_STATE,
            value_signature: pattern.state.to_owned(),
            anchor_offset,
            confidence: pattern.confidence,
            cue_bitmap,
            change_salience: 1.0,
        });
        break;
    }
    claims
}

fn extract_owner_claims(
    search_window: &ClaimSearchWindow<'_>,
    matched: &AliasMatch,
    patterns: &AliasPatternSet,
    canonical_name_by_surface: &HashMap<String, String>,
    script_mode: &str,
) -> Vec<ClaimCandidate> {
    let mut claims = Vec::new();
    let regex = if script_mode == SCRIPT_MODE_CJK_HEAVY {
        &patterns.zh_owner
    } else {
        &patterns.en_owner
    };
    if let Some(value_match) = regex
        .captures(search_window.text)
        .and_then(|captures| captures.name("value"))
    {
        push_normalized_claim(
            &mut claims,
            search_window,
            matched,
            value_match,
            SLOT_ARTIFACT_CURRENT_OWNER,
            canonical_name_by_surface,
            0.9,
            1.0,
        );
    }
    claims
}

fn build_zh_location_value_body() -> String {
    let mut suffixes: Vec<&str> = LOCATION_SUFFIXES_ZH.to_vec();
    suffixes.extend(EXTRA_LOCATION_SUFFIXES_ZH.iter().copied());
    sort_longest_first(&mut suffixes);
    format!(
        r"[^，。！？；：、“”‘’（）()\n]{{0,14}}(?:{})(?:里|中|内|外|上|下)?",
        join_regex_alternation(&suffixes),
    )
}

fn build_zh_affiliation_value_body() -> String {
    let mut suffixes: Vec<&str> = AFFILIATION_SUFFIXES_ZH.to_vec();
    suffixes.extend(EXTRA_AFFILIATION_SUFFIXES_ZH.iter().copied());
    sort_longest_first(&mut suffixes);
    format!(
        r"[^，。！？；：、“”‘’（）()\n]{{0,12}}(?:{})",
        join_regex_alternation(&suffixes),
    )
}

fn build_en_structured_value_body() -> String {
    r"[A-Z][A-Za-z0-9']*(?:[ -](?:[A-Z][A-Za-z0-9']*|(?:of|the|de|du|van|von))){0,5}".to_owned()
}

fn build_life_state_patterns(
    alias: &str,
    cjk_heavy: bool,
    specs: &[(&'static str, &[&'static str], f64)],
) -> Result<Vec<LifeStatePattern>, PayloadError> {
    let mut patterns = Vec::new();
    for (state, needles, confidence) in specs {
        for needle in *needles {
            let raw = if cjk_heavy {
                format!(
                    r"\A{alias}(?:如今|现在|已经|已|还|仍|仍然|就|也|便|却)?[^，。！？；：\n]{{0,4}}{needle}",
                    alias = alias,
                    needle = regex::escape(needle),
                )
            } else {
                format!(
                    r"\A{alias}[^。！？!\n]{{0,12}}{needle}",
                    alias = alias,
                    needle = regex::escape(needle),
                )
            };
            patterns.push(LifeStatePattern {
                state,
                confidence: *confidence,
                regex: compile_ci_regex(&raw)?,
            });
        }
    }
    Ok(patterns)
}

fn compile_regex(raw: &str) -> Result<Regex, PayloadError> {
    Regex::new(raw).map_err(|err| PayloadError::InvalidRequest(err.to_string()))
}

fn compile_ci_regex(raw: &str) -> Result<Regex, PayloadError> {
    RegexBuilder::new(raw)
        .case_insensitive(true)
        .build()
        .map_err(|err| PayloadError::InvalidRequest(err.to_string()))
}

fn join_regex_alternation(items: &[&str]) -> String {
    items
        .iter()
        .map(|item| regex::escape(item))
        .collect::<Vec<_>>()
        .join("|")
}

fn sort_longest_first(items: &mut Vec<&str>) {
    items.sort_by(|left, right| right.len().cmp(&left.len()).then_with(|| left.cmp(right)));
    items.dedup();
}

fn normalize_value_signature(
    value: &str,
    slot: &str,
    canonical_name_by_surface: &HashMap<String, String>,
) -> Option<String> {
    let mut cleaned = value
        .trim_matches(|ch| VALUE_STOP_CHARS.contains(ch))
        .trim()
        .to_owned();
    cleaned = strip_leading_value_noise(&cleaned);
    cleaned = strip_trailing_latin_value_noise(&cleaned);
    if slot == SLOT_ENTITY_CURRENT_LOCATION {
        if let Some((_, tail)) = cleaned.rsplit_once('的') {
            cleaned = tail.trim().to_owned();
        }
        cleaned = trim_with_suffixes(&cleaned, LOCATION_SUFFIXES_ZH);
        cleaned = cleaned
            .trim_end_matches(|ch| TRAILING_LOCATION_TRIM.contains(ch))
            .to_owned();
        if DETERMINER_RE.is_match(&cleaned) {
            return None;
        }
    } else if slot == SLOT_ENTITY_CURRENT_AFFILIATION {
        if let Some((_, tail)) = cleaned.rsplit_once('的') {
            cleaned = tail.trim().to_owned();
        }
        cleaned = trim_with_suffixes(&cleaned, AFFILIATION_SUFFIXES_ZH);
    }
    cleaned = cleaned.trim().to_owned();
    if cleaned.is_empty() {
        return None;
    }
    if let Some(canonical) = canonical_name_by_surface.get(&cleaned) {
        return Some(canonical.clone());
    }
    if slot == SLOT_ENTITY_LIFE_STATE {
        return Some(cleaned.to_ascii_lowercase());
    }
    Some(cleaned)
}

fn strip_leading_value_noise(value: &str) -> String {
    let mut cleaned = value.trim().to_owned();
    let mut changed = true;
    while changed && !cleaned.is_empty() {
        changed = false;
        for prefix in LEADING_VALUE_PREFIXES {
            if cleaned.starts_with(prefix) && cleaned.len() > prefix.len() {
                cleaned = cleaned[prefix.len()..].trim().to_owned();
                changed = true;
                break;
            }
        }
    }
    cleaned
}

fn strip_trailing_latin_value_noise(value: &str) -> String {
    let cleaned = value.trim();
    if cleaned.is_empty() || cleaned.chars().any(is_cjk) {
        return cleaned.to_owned();
    }
    let mut tokens: Vec<&str> = cleaned.split_whitespace().collect();
    while let Some(last) = tokens.last().copied() {
        let raw_last = last.trim_matches(|ch| ch == '\'' || ch == '"' || ch == '-');
        let normalized_last = raw_last.to_ascii_lowercase();
        if raw_last.is_empty() {
            tokens.pop();
            continue;
        }
        if LATIN_VALUE_CONNECTORS.contains(&normalized_last.as_str())
            || raw_last.chars().all(|ch| !ch.is_uppercase())
        {
            tokens.pop();
            continue;
        }
        break;
    }
    tokens.join(" ").trim().to_owned()
}

fn trim_with_suffixes(value: &str, suffixes: &[&str]) -> String {
    if value.is_empty() {
        return value.to_owned();
    }
    let mut best_end = None;
    for suffix in suffixes {
        if let Some(pos) = value.find(suffix) {
            let end = pos + suffix.len();
            best_end = Some(best_end.map_or(end, |current| usize::max(current, end)));
        }
    }
    if let Some(end) = best_end {
        value[..end].to_owned()
    } else {
        value.to_owned()
    }
}

fn detect_cue_bitmap(text: &IndexedTextSlice<'_>, start: usize, end: usize) -> i64 {
    let mut context_start = start;
    while context_start > 0 && !CUE_CONTEXT_BREAKS.contains(text.chars[context_start - 1]) {
        context_start -= 1;
    }
    let mut context_end = usize::min(end, text.char_len());
    while context_end < text.char_len() && !CUE_CONTEXT_BREAKS.contains(text.chars[context_end]) {
        context_end += 1;
    }
    let context = text.slice(context_start, context_end).to_lowercase();
    let mut flags = 0;
    if HISTORICAL_TERMS
        .iter()
        .any(|term| context.contains(&term.to_lowercase()))
    {
        flags |= CUE_HISTORICAL;
    }
    if HYPOTHETICAL_TERMS
        .iter()
        .any(|term| context.contains(&term.to_lowercase()))
    {
        flags |= CUE_HYPOTHETICAL;
    }
    if NEGATION_TERMS
        .iter()
        .any(|term| context.contains(&term.to_lowercase()))
    {
        flags |= CUE_NEGATED;
    }
    if flags == 0 {
        flags |= CUE_ASSERTED;
    }
    flags
}

fn merge_claims(existing: &ClaimData, candidate: &ClaimData) -> ClaimData {
    let preferred = if (existing.confidence, -existing.anchor_offset)
        >= (candidate.confidence, -candidate.anchor_offset)
    {
        existing
    } else {
        candidate
    };
    ClaimData {
        claim_id: 0,
        target_id: preferred.target_id.clone(),
        slot: preferred.slot.clone(),
        value_signature: preferred.value_signature.clone(),
        segment_id: preferred.segment_id,
        chapter_number: preferred.chapter_number,
        anchor_offset: preferred.anchor_offset,
        confidence: existing.confidence.max(candidate.confidence),
        cue_bitmap: existing.cue_bitmap | candidate.cue_bitmap,
        change_salience: existing.change_salience.max(candidate.change_salience),
    }
}

fn dedupe_alias_matches(matches: &[AliasMatch]) -> Vec<AliasMatch> {
    let mut ordered = matches.to_vec();
    ordered.sort_by(|left, right| {
        (left.start, left.end, left.alias.as_str()).cmp(&(
            right.start,
            right.end,
            right.alias.as_str(),
        ))
    });
    ordered.dedup_by(|left, right| {
        left.start == right.start && left.end == right.end && left.alias == right.alias
    });
    ordered
}
