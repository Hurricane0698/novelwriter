use aho_corasick::AhoCorasick;
use regex::{Regex, RegexBuilder};
use serde::{Deserialize, Serialize};
use std::cell::RefCell;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::rc::Rc;
use std::time::Instant;

mod claim;
mod incremental;
mod mention;
mod payload;
mod segment;

pub use incremental::{assemble_payload_bytes, build_full, plan_update_result, update_incremental};
pub(crate) use segment::{normalize_chapter_text, segment_chapter_text_without_index};

use claim::AliasPatternSet;
use mention::AliasEntry;
use segment::is_cjk_language;

pub const STATE_PROTO_PAYLOAD_KIND: &str = "state_proto";
pub const STATE_PROTO_PAYLOAD_FORMAT_VERSION: u32 = 2;
const DEFAULT_PROGRESS_BUCKETS: i64 = 8;
const STATE_PROTO_SEGMENT_ID_SHIFT: i64 = 16;
const STATE_PROTO_CLAIM_ID_SHIFT: i64 = 20;

const SCRIPT_MODE_CJK_HEAVY: &str = "cjk_heavy";
const SCRIPT_MODE_SPACE_DELIMITED: &str = "space_delimited";

const TARGET_KIND_ENTITY: &str = "entity";
const TARGET_KIND_ARTIFACT: &str = "artifact";

const SLOT_ENTITY_CURRENT_LOCATION: &str = "entity.current_location";
const SLOT_ENTITY_CURRENT_AFFILIATION: &str = "entity.current_affiliation";
const SLOT_ENTITY_CURRENT_ROLE: &str = "entity.current_role";
const SLOT_ENTITY_LIFE_STATE: &str = "entity.life_state";
const SLOT_ARTIFACT_CURRENT_OWNER: &str = "artifact.current_owner";

const CUE_ASSERTED: i64 = 1 << 0;
const CUE_HISTORICAL: i64 = 1 << 1;
const CUE_HYPOTHETICAL: i64 = 1 << 2;
const CUE_NEGATED: i64 = 1 << 3;

const DEFAULT_SEGMENT_MIN_CHARS: usize = 220;
const DEFAULT_SEGMENT_SOFT_MAX_CHARS: usize = 520;
const DEFAULT_SEGMENT_HARD_MAX_CHARS: usize = 700;
const DEFAULT_SEGMENT_TAIL_MERGE_CHARS: usize = 160;
const DEFAULT_SEGMENT_MERGED_MAX_CHARS: usize = 820;

const VALUE_STOP_CHARS: &str = "，。！？；：、“”‘’（）()[]{}<>《》「」『』\n\r\t";
const TRAILING_LOCATION_TRIM: &str = "里中处内外上下";
const CUE_CONTEXT_BREAKS: &str = "，,。！？；：:、\n";

const SENTENCE_CLOSERS: &[char] = &['"', '\'', '”', '’', '」', '』', '）', '】', '》'];
const CJK_SENTENCE_TERMINATORS: &[char] = &['。', '！', '？', '；', '…'];
const NON_CJK_SENTENCE_TERMINATORS: &[char] = &['.', '?', '!', ';', ':'];
const LEADING_VALUE_PREFIXES: &[&str] = &[
    "并不是",
    "不是",
    "并非",
    "不在",
    "没有",
    "未在",
    "并不",
    "不再",
    "非",
    "了",
    "着",
    "过",
    "又",
    "还",
    "仍",
    "正",
    "就",
    "便",
    "却",
    "都",
    "也",
];
const LATIN_VALUE_CONNECTORS: &[&str] = &["of", "the", "de", "du", "van", "von"];

const ROLE_KEYWORDS_ZH: &[&str] = &[
    "大长老",
    "长老",
    "门主",
    "掌门",
    "城主",
    "队长",
    "统领",
    "侍女",
    "弟子",
    "护卫",
    "掌柜",
    "账房",
    "信使",
    "先生",
    "老师",
    "师父",
    "族长",
    "少主",
];
const ROLE_KEYWORDS_EN: &[&str] = &[
    "captain",
    "commander",
    "master",
    "teacher",
    "guard",
    "keeper",
    "messenger",
    "clerk",
];
const LOCATION_SUFFIXES_ZH: &[&str] = &[
    "旧街", "码头", "书院", "后院", "前院", "城门", "城", "街", "巷", "门", "司", "院", "阁", "楼",
    "坊", "铺", "堂", "宫", "殿", "桥", "寨", "营", "镇", "村", "山", "谷", "河", "湖", "港",
    "港口",
];
const EXTRA_LOCATION_SUFFIXES_ZH: &[&str] = &[
    "桥头", "门口", "入口", "出口", "家", "家里", "家中", "室", "室内", "屋内", "屋外", "厅",
    "大厅", "房", "房内", "馆", "公司", "公寓", "旅馆", "酒吧", "教堂",
];
const AFFILIATION_SUFFIXES_ZH: &[&str] =
    &["宗", "门", "会", "帮", "派", "盟", "营", "司", "府", "书院"];
const EXTRA_AFFILIATION_SUFFIXES_ZH: &[&str] = &["组织"];

const HISTORICAL_TERMS: &[&str] = &[
    "曾",
    "曾经",
    "从前",
    "过去",
    "此前",
    "之前",
    "当年",
    "昔日",
    "once",
    "formerly",
    "previously",
    "used to",
];
const HYPOTHETICAL_TERMS: &[&str] = &[
    "若", "如果", "假如", "或许", "也许", "可能", "传言", "听说", "据说", "rumor", "maybe",
    "might", "could", "would", "if ",
];
const NEGATION_TERMS: &[&str] = &[
    "不在",
    "并非",
    "不是",
    "没有",
    "未在",
    "no longer",
    "not ",
    "never",
    "without",
];

const LIFE_STATE_ZH_DEAD: &[&str] = &["死了", "已死", "身亡", "死亡", "殒命", "丧命"];
const LIFE_STATE_ZH_MISSING: &[&str] = &["失踪", "下落不明"];
const LIFE_STATE_ZH_INCAPACITATED: &[&str] = &["昏迷", "重伤昏迷", "失去意识", "瘫倒"];
const LIFE_STATE_ZH_ALIVE: &[&str] = &["还活着", "仍活着", "活着", "活了下来"];
const LIFE_STATE_EN_DEAD: &[&str] = &["is dead", "was killed", "died"];
const LIFE_STATE_EN_MISSING: &[&str] = &["is missing", "went missing"];
const LIFE_STATE_EN_INCAPACITATED: &[&str] = &["is unconscious", "is incapacitated"];
const LIFE_STATE_EN_ALIVE: &[&str] = &["is alive", "stays alive"];

#[derive(Debug, thiserror::Error)]
pub enum PayloadError {
    #[error("invalid request: {0}")]
    InvalidRequest(String),
    #[error("invalid payload: {0}")]
    InvalidPayload(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RequestTarget {
    pub id: String,
    pub canonical_name: String,
    #[serde(default = "default_target_kind")]
    pub kind: String,
    #[serde(default)]
    pub aliases: Vec<String>,
}

impl RequestTarget {
    fn all_aliases(&self) -> Vec<String> {
        let mut ordered = Vec::with_capacity(self.aliases.len() + 1);
        ordered.push(self.canonical_name.clone());
        ordered.extend(self.aliases.iter().cloned());
        let mut seen = HashSet::new();
        let mut deduped = Vec::new();
        for alias in ordered {
            let trimmed = alias.trim();
            if trimmed.is_empty() || !seen.insert(trimmed.to_owned()) {
                continue;
            }
            deduped.push(trimmed.to_owned());
        }
        deduped
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RequestChapter {
    pub chapter_id: i64,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub signature: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BuildRequest {
    pub format_version: u32,
    #[serde(default)]
    pub requested_language: Option<String>,
    #[serde(default)]
    pub chapters: Vec<RequestChapter>,
    #[serde(default)]
    pub targets: Vec<RequestTarget>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChapterShard {
    pub chapter_id: i64,
    pub chapter_number: i64,
    #[serde(default)]
    pub signature: Option<String>,
    #[serde(default)]
    pub segments: Vec<SegmentRow>,
    #[serde(default)]
    pub mentions: Vec<MentionRow>,
    #[serde(default)]
    pub claims: Vec<ClaimRow>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PayloadWire {
    pub kind: String,
    pub v: u32,
    pub language: String,
    #[serde(default)]
    pub targets: Vec<TargetWire>,
    #[serde(default)]
    pub chapters: Vec<ChapterShard>,
    #[serde(default)]
    pub coverage: Vec<CoverageRow>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TargetWire(pub String, pub String, pub String, pub Vec<String>);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentRow(
    pub i64,
    pub i64,
    pub i64,
    pub i64,
    pub i64,
    pub i64,
    pub Option<i64>,
    pub Option<i64>,
);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MentionRow(pub String, pub i64, pub f64, pub f64, pub i64);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaimRow(
    pub i64,
    pub String,
    pub String,
    pub String,
    pub i64,
    pub i64,
    pub i64,
    pub f64,
    pub i64,
    pub f64,
);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoverageRow(pub String, pub i64, pub i64, pub f64);

#[derive(Debug, Serialize)]
pub struct UpdatePlanResult {
    pub mode: String,
    pub supported_incremental: bool,
    pub existing_payload_compatible: bool,
    pub target_catalog_changed: bool,
    pub dirty_chapter_ids: Vec<i64>,
    pub fallback_reason: Option<String>,
    pub no_changes: bool,
}

#[derive(Debug, Serialize)]
pub struct AssembleResult {
    pub payload_bytes: usize,
    pub chapter_count: usize,
    pub target_count: usize,
    pub segment_count: usize,
    pub mention_posting_count: usize,
    pub claim_atom_count: usize,
    pub coverage_rep_count: usize,
    pub rebuilt_chapter_count: usize,
    pub reused_chapter_count: usize,
    pub incremental_applied: bool,
}

#[derive(Debug, Serialize)]
pub struct BuildResult {
    pub payload_bytes: usize,
    pub chapter_count: usize,
    pub chapter_chars: usize,
    pub target_count: usize,
    pub segment_count: usize,
    pub mention_posting_count: usize,
    pub claim_atom_count: usize,
    pub coverage_rep_count: usize,
    pub segmentation_ms: f64,
    pub mention_ms: f64,
    pub claim_ms: f64,
    pub coverage_ms: f64,
    pub serialize_ms: f64,
    pub duration_ms: f64,
    pub plan_mode: String,
    pub incremental_applied: bool,
    pub rebuilt_chapter_count: usize,
    pub reused_chapter_count: usize,
    pub fallback_reason: Option<String>,
}

#[derive(Debug, Clone)]
pub(crate) struct SegmentData {
    pub(crate) segment_id: i64,
    pub(crate) chapter_id: i64,
    pub(crate) chapter_number: i64,
    pub(crate) start_pos: i64,
    pub(crate) end_pos: i64,
    pub(crate) progress_bucket: i64,
    pub(crate) prev_segment_id: Option<i64>,
    pub(crate) next_segment_id: Option<i64>,
}

#[derive(Debug, Clone)]
struct MentionData {
    target_id: String,
    segment_id: i64,
    mention_score: f64,
    density: f64,
    best_anchor_offset: i64,
}

#[derive(Debug, Clone)]
struct ClaimData {
    claim_id: i64,
    target_id: String,
    slot: String,
    value_signature: String,
    segment_id: i64,
    chapter_number: i64,
    anchor_offset: i64,
    confidence: f64,
    cue_bitmap: i64,
    change_salience: f64,
}

#[derive(Debug, Clone)]
struct CoverageData {
    target_id: String,
    bucket_id: i64,
    segment_id: i64,
    rep_score: f64,
}

#[derive(Debug, Clone)]
struct ChapterShardData {
    chapter_id: i64,
    chapter_number: i64,
    signature: Option<String>,
    segments: Vec<SegmentData>,
    mentions: Vec<MentionData>,
    claims: Vec<ClaimData>,
}

#[derive(Debug, Default, Clone, Copy)]
struct StageStats {
    segmentation_ms: f64,
    mention_ms: f64,
    claim_ms: f64,
}

#[derive(Debug)]
struct BuildContext {
    targets_by_id: HashMap<String, RequestTarget>,
    alias_entries: Vec<AliasEntry>,
    alias_automaton: Option<AhoCorasick>,
    alias_patterns: RefCell<AliasPatternCache>,
    canonical_name_by_surface: HashMap<String, String>,
    cjk_language: bool,
}

impl BuildContext {
    fn get_alias_patterns(&self, alias: &str) -> Result<Rc<AliasPatternSet>, PayloadError> {
        self.alias_patterns.borrow_mut().get_or_build(alias)
    }
}

#[derive(Debug, Default)]
struct AliasPatternCache {
    entries: HashMap<String, Rc<AliasPatternSet>>,
}

impl AliasPatternCache {
    fn get_or_build(&mut self, alias: &str) -> Result<Rc<AliasPatternSet>, PayloadError> {
        if let Some(existing) = self.entries.get(alias) {
            return Ok(existing.clone());
        }
        let built = Rc::new(AliasPatternSet::build(alias)?);
        self.entries.insert(alias.to_owned(), built.clone());
        Ok(built)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn alias_pattern_cache_keeps_alias_patterns_for_entire_build() {
        let mut cache = AliasPatternCache::default();
        let first = cache
            .get_or_build("人物0")
            .expect("first alias pattern should build");

        for index in 1..64 {
            cache
                .get_or_build(&format!("人物{index}"))
                .expect("later alias pattern should build");
        }

        let first_again = cache
            .get_or_build("人物0")
            .expect("first alias pattern should stay cached");

        assert!(Rc::ptr_eq(&first, &first_again));
        assert_eq!(cache.entries.len(), 64);
    }
}

#[derive(Debug, Clone)]
struct IndexedText {
    text: String,
    chars: Vec<char>,
    char_to_byte: Vec<usize>,
}

impl IndexedText {
    fn new(text: String) -> Self {
        let mut chars = Vec::new();
        let mut char_to_byte = Vec::new();
        for (idx, ch) in text.char_indices() {
            char_to_byte.push(idx);
            chars.push(ch);
        }
        char_to_byte.push(text.len());
        Self {
            text,
            chars,
            char_to_byte,
        }
    }

    fn char_len(&self) -> usize {
        self.chars.len()
    }

    fn char_to_byte(&self, char_idx: usize) -> usize {
        *self.char_to_byte.get(char_idx).unwrap_or(&self.text.len())
    }

    fn slice(&self, start: usize, end: usize) -> &str {
        let start_byte = *self.char_to_byte.get(start).unwrap_or(&self.text.len());
        let end_byte = *self.char_to_byte.get(end).unwrap_or(&self.text.len());
        &self.text[start_byte..end_byte]
    }

    fn byte_to_char(&self, byte_idx: usize) -> usize {
        match self.char_to_byte.binary_search(&byte_idx) {
            Ok(idx) => idx,
            Err(idx) => idx,
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct IndexedTextSlice<'a> {
    parent: &'a IndexedText,
    text: &'a str,
    chars: &'a [char],
    start_char: usize,
    start_byte: usize,
    end_char: usize,
}

impl<'a> IndexedTextSlice<'a> {
    fn new(parent: &'a IndexedText, start_char: usize, end_char: usize) -> Self {
        let start_byte = parent.char_to_byte(start_char);
        let end_byte = parent.char_to_byte(end_char);
        Self {
            parent,
            text: &parent.text[start_byte..end_byte],
            chars: &parent.chars[start_char..end_char],
            start_char,
            start_byte,
            end_char,
        }
    }

    fn char_len(&self) -> usize {
        self.end_char.saturating_sub(self.start_char)
    }

    fn slice(&self, start: usize, end: usize) -> &str {
        self.parent.slice(
            self.start_char.saturating_add(start),
            self.start_char.saturating_add(end),
        )
    }

    fn byte_to_char(&self, byte_idx: usize) -> usize {
        self.parent.byte_to_char(self.start_byte + byte_idx) - self.start_char
    }
}

impl SegmentData {
    fn to_row(&self) -> SegmentRow {
        SegmentRow(
            self.segment_id,
            self.chapter_id,
            self.chapter_number,
            self.start_pos,
            self.end_pos,
            self.progress_bucket,
            self.prev_segment_id,
            self.next_segment_id,
        )
    }

    fn from_row(row: &SegmentRow) -> Self {
        Self {
            segment_id: row.0,
            chapter_id: row.1,
            chapter_number: row.2,
            start_pos: row.3,
            end_pos: row.4,
            progress_bucket: row.5,
            prev_segment_id: row.6,
            next_segment_id: row.7,
        }
    }
}

impl MentionData {
    fn to_row(&self) -> MentionRow {
        MentionRow(
            self.target_id.clone(),
            self.segment_id,
            round_places(self.mention_score, 4),
            round_places(self.density, 6),
            self.best_anchor_offset,
        )
    }

    fn from_row(row: &MentionRow) -> Self {
        Self {
            target_id: row.0.clone(),
            segment_id: row.1,
            mention_score: row.2,
            density: row.3,
            best_anchor_offset: row.4,
        }
    }
}

impl ClaimData {
    fn to_row(&self) -> ClaimRow {
        ClaimRow(
            self.claim_id,
            self.target_id.clone(),
            self.slot.clone(),
            self.value_signature.clone(),
            self.segment_id,
            self.chapter_number,
            self.anchor_offset,
            round_places(self.confidence, 4),
            self.cue_bitmap,
            round_places(self.change_salience, 4),
        )
    }

    fn from_row(row: &ClaimRow) -> Self {
        Self {
            claim_id: row.0,
            target_id: row.1.clone(),
            slot: row.2.clone(),
            value_signature: row.3.clone(),
            segment_id: row.4,
            chapter_number: row.5,
            anchor_offset: row.6,
            confidence: row.7,
            cue_bitmap: row.8,
            change_salience: row.9,
        }
    }
}

impl CoverageData {
    fn to_row(&self) -> CoverageRow {
        CoverageRow(
            self.target_id.clone(),
            self.bucket_id,
            self.segment_id,
            round_places(self.rep_score, 4),
        )
    }
}

impl ChapterShardData {
    fn to_wire(&self) -> ChapterShard {
        ChapterShard {
            chapter_id: self.chapter_id,
            chapter_number: self.chapter_number,
            signature: self.signature.clone(),
            segments: self.segments.iter().map(SegmentData::to_row).collect(),
            mentions: self.mentions.iter().map(MentionData::to_row).collect(),
            claims: self.claims.iter().map(ClaimData::to_row).collect(),
        }
    }

    fn from_wire(wire: &ChapterShard) -> Self {
        Self {
            chapter_id: wire.chapter_id,
            chapter_number: wire.chapter_number,
            signature: wire.signature.clone(),
            segments: wire.segments.iter().map(SegmentData::from_row).collect(),
            mentions: wire.mentions.iter().map(MentionData::from_row).collect(),
            claims: wire.claims.iter().map(ClaimData::from_row).collect(),
        }
    }
}

fn default_target_kind() -> String {
    TARGET_KIND_ENTITY.to_owned()
}

fn round_ms(value: f64) -> f64 {
    round_places(value, 1)
}

fn round_places(value: f64, places: usize) -> f64 {
    let factor = 10f64.powi(places as i32);
    (value * factor).round() / factor
}

pub fn decode_request(data: &[u8]) -> Result<BuildRequest, PayloadError> {
    let request: BuildRequest = serde_json::from_slice(data)
        .map_err(|err| PayloadError::InvalidRequest(err.to_string()))?;
    if request.format_version == 0 {
        return Err(PayloadError::InvalidRequest(
            "missing format_version".to_owned(),
        ));
    }
    Ok(request)
}

pub fn decode_payload(data: &[u8]) -> Result<PayloadWire, PayloadError> {
    let payload: PayloadWire = match rmp_serde::from_slice(data) {
        Ok(payload) => payload,
        Err(_) => serde_json::from_slice(data)
            .map_err(|err| PayloadError::InvalidPayload(err.to_string()))?,
    };
    if payload.kind != STATE_PROTO_PAYLOAD_KIND {
        return Err(PayloadError::InvalidPayload(
            "legacy or unknown payload kind".to_owned(),
        ));
    }
    Ok(payload)
}

fn serialize_payload(payload: &PayloadWire) -> Result<Vec<u8>, PayloadError> {
    rmp_serde::to_vec_named(payload).map_err(|err| PayloadError::InvalidPayload(err.to_string()))
}

fn request_targets_as_wire(targets: &[RequestTarget]) -> Vec<TargetWire> {
    targets
        .iter()
        .map(|target| {
            let mut aliases = target.aliases.clone();
            aliases.sort();
            aliases.dedup();
            TargetWire(
                target.id.clone(),
                target.kind.clone(),
                target.canonical_name.clone(),
                aliases,
            )
        })
        .collect()
}

fn count_payload(payload: &PayloadWire) -> (usize, usize, usize, usize, usize) {
    let segment_count = payload
        .chapters
        .iter()
        .map(|chapter| chapter.segments.len())
        .sum();
    let mention_count = payload
        .chapters
        .iter()
        .map(|chapter| chapter.mentions.len())
        .sum();
    let claim_count = payload
        .chapters
        .iter()
        .map(|chapter| chapter.claims.len())
        .sum();
    (
        payload.targets.len(),
        segment_count,
        mention_count,
        claim_count,
        payload.coverage.len(),
    )
}

fn resolve_language(requested_language: Option<&str>) -> String {
    let trimmed = requested_language.unwrap_or("zh").trim();
    if trimmed.is_empty() {
        "zh".to_owned()
    } else {
        trimmed.to_ascii_lowercase()
    }
}

fn build_context(targets: &[RequestTarget], language: &str) -> Result<BuildContext, PayloadError> {
    let mut targets_by_id = HashMap::new();
    let mut alias_entries = Vec::new();
    let mut canonical_name_by_surface = HashMap::new();
    let mut seen_aliases = HashSet::new();
    for target in targets {
        targets_by_id.insert(target.id.clone(), target.clone());
        canonical_name_by_surface
            .entry(target.canonical_name.clone())
            .or_insert_with(|| target.canonical_name.clone());
        for alias in target.all_aliases() {
            if !seen_aliases.insert(alias.clone()) {
                continue;
            }
            canonical_name_by_surface
                .entry(alias.clone())
                .or_insert_with(|| target.canonical_name.clone());
            alias_entries.push(AliasEntry {
                target_id: target.id.clone(),
                alias,
            });
        }
    }
    let alias_automaton = if alias_entries.is_empty() {
        None
    } else {
        Some(
            AhoCorasick::new(
                alias_entries
                    .iter()
                    .map(|entry| entry.alias.as_str())
                    .collect::<Vec<_>>(),
            )
            .map_err(|err| PayloadError::InvalidRequest(err.to_string()))?,
        )
    };
    Ok(BuildContext {
        targets_by_id,
        alias_entries,
        alias_automaton,
        alias_patterns: RefCell::new(AliasPatternCache::default()),
        canonical_name_by_surface,
        cjk_language: is_cjk_language(language),
    })
}

#[derive(Debug)]
struct PayloadCounts {
    segment_count: usize,
    mention_posting_count: usize,
    claim_atom_count: usize,
    coverage_rep_count: usize,
    rebuilt_chapter_count: usize,
    reused_chapter_count: usize,
    incremental_applied: bool,
}
