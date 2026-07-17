from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2s
import re
from typing import TYPE_CHECKING

from app.core.state_proto_contract import STATE_PROTO_PAYLOAD_FORMAT_VERSION

if TYPE_CHECKING:
    from .state_proto_runtime import StateProtoIndex

STATE_PROTO_PAYLOAD_KIND = "state_proto"
STATE_PROTO_COMPACT_FORMAT_VERSION = STATE_PROTO_PAYLOAD_FORMAT_VERSION
STATE_PROTO_EXECUTOR_STATE_FRESH = "fresh"
STATE_PROTO_EXECUTOR_STATE_MISSING = "missing"
STATE_PROTO_EXECUTOR_BACKEND_NONE = "none"
STATE_PROTO_EXECUTOR_BACKEND_RUST = "rust"

SCRIPT_MODE_CJK_HEAVY = "cjk_heavy"
SCRIPT_MODE_SPACE_DELIMITED = "space_delimited"

TARGET_KIND_ENTITY = "entity"
TARGET_KIND_ARTIFACT = "artifact"
TARGET_KIND_RELATIONSHIP = "relationship"
TARGET_KIND_SYSTEM = "system"

SLOT_ENTITY_CURRENT_LOCATION = "entity.current_location"
SLOT_ENTITY_CURRENT_AFFILIATION = "entity.current_affiliation"
SLOT_ENTITY_CURRENT_ROLE = "entity.current_role"
SLOT_ENTITY_LIFE_STATE = "entity.life_state"
SLOT_ARTIFACT_CURRENT_OWNER = "artifact.current_owner"

SUPPORTED_CLAIM_SLOTS = frozenset(
    {
        SLOT_ENTITY_CURRENT_LOCATION,
        SLOT_ENTITY_CURRENT_AFFILIATION,
        SLOT_ENTITY_CURRENT_ROLE,
        SLOT_ENTITY_LIFE_STATE,
        SLOT_ARTIFACT_CURRENT_OWNER,
    }
)

UNCERTAINTY_LOW_MARGIN = "low_margin"
UNCERTAINTY_FRESH_CONFLICT = "fresh_conflict"
UNCERTAINTY_SPARSE_TAIL = "sparse_tail"
UNCERTAINTY_AMBIGUOUS_CUE = "ambiguous_cue"

CUE_ASSERTED = 1 << 0
CUE_HISTORICAL = 1 << 1
CUE_HYPOTHETICAL = 1 << 2
CUE_NEGATED = 1 << 3

DEFAULT_SEGMENT_MIN_CHARS = 220
DEFAULT_SEGMENT_TARGET_CHARS = 420
DEFAULT_SEGMENT_SOFT_MAX_CHARS = 520
DEFAULT_SEGMENT_HARD_MAX_CHARS = 700
DEFAULT_SEGMENT_TAIL_MERGE_CHARS = 160
DEFAULT_SEGMENT_MERGED_MAX_CHARS = 820
DEFAULT_PROGRESS_BUCKETS = 8
DEFAULT_DISCOVERY_SHORTLIST_MULTIPLIER = 8
DEFAULT_DISCOVERY_CUE_SCORE_CAP = 12
DEFAULT_CJK_PREVIEW_CHARS = 40
DEFAULT_NON_CJK_PREVIEW_CHARS = 80
DEFAULT_CJK_OPEN_CHARS = 220
DEFAULT_NON_CJK_OPEN_CHARS = 420

_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_WHITESPACE_RE = re.compile(r"\s+")
_CJK_SENTENCE_TERMINATORS = frozenset("。！？；…")
_NON_CJK_SENTENCE_TERMINATORS = frozenset(".?!;:")
_SENTENCE_CLOSERS = frozenset("\"'”’」』）】》]")
_VALUE_STOP_CHARS = "，。！？；：、“”‘’（）()[]{}<>《》「」『』\n\r\t"
_ROLE_KEYWORDS_ZH = (
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
)
_ROLE_KEYWORDS_EN = (
    "captain",
    "commander",
    "master",
    "teacher",
    "guard",
    "keeper",
    "messenger",
    "clerk",
)
_LOCATION_SUFFIXES_ZH = (
    "旧街",
    "码头",
    "书院",
    "后院",
    "前院",
    "城门",
    "城",
    "街",
    "巷",
    "门",
    "司",
    "院",
    "阁",
    "楼",
    "坊",
    "铺",
    "堂",
    "宫",
    "殿",
    "桥",
    "寨",
    "营",
    "镇",
    "村",
    "山",
    "谷",
    "河",
    "湖",
    "港",
    "港口",
)
_AFFILIATION_SUFFIXES_ZH = (
    "宗",
    "门",
    "会",
    "帮",
    "派",
    "盟",
    "营",
    "司",
    "府",
    "书院",
)
_HISTORICAL_TERMS = (
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
)
_HYPOTHETICAL_TERMS = (
    "若",
    "如果",
    "假如",
    "或许",
    "也许",
    "可能",
    "传言",
    "听说",
    "据说",
    "rumor",
    "maybe",
    "might",
    "could",
    "would",
    "if ",
)
_NEGATION_TERMS = (
    "不在",
    "并非",
    "不是",
    "没有",
    "未在",
    "no longer",
    "not ",
    "never",
    "without",
)
_ZH_GENERIC_TARGET_BLOCKLIST = frozenset(
    {
        "先生",
        "先生们",
        "小姐",
        "女士",
        "女士们",
        "男士",
        "夫人",
        "太太",
        "阁下",
        "大人",
        "非凡",
        "序列",
        "途径",
        "占卜",
        "天使",
        "教会",
        "魔药",
        "物品",
        "真个",
        "认得",
        "怎生",
        "依然",
        "忽然",
        "果然",
        "只是",
        "若是",
        "如何",
        "贫僧",
        "甚么",
        "无比",
        "一名",
        "弟子",
        "身影",
        "玄力",
        "之力",
        "神界",
        "文明",
        "宇宙",
        "信息",
        "人类",
        "地球",
        "太阳",
        "科学",
        "研究",
        "系统",
        "运行",
        "深渊",
        "可怕",
        "面对",
        "他们",
        "一路",
        "消失",
        "出现",
        "想要",
        "玄者",
        "天神",
        "基地",
        "发射",
        "纪元",
        "三体",
        "世界",
        "凤凰",
        "神帝",
        "质子",
        "智子",
        "肯定",
        "背景",
        "计算机",
        "游戏",
        "灰雾",
        "贝克兰",
        "金乌",
        "天线",
        "组织",
        "倒计时",
        "元首",
        "快速",
        "目标",
        "社会",
        "金字塔",
        "天空",
        "生活",
        "计算",
        "长老",
        "火焰",
        "灵魂",
        "大陆",
        "封印",
        "特性",
        "神秘",
        "展开",
        "行星",
        "执政官",
        "生存",
    }
)
_EN_GENERIC_TARGET_BLOCKLIST = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "sir",
        "lady",
        "angel",
        "sequence",
        "pathway",
        "potion",
        "item",
    }
)
_LOCATION_SUFFIX_PATTERN_ZH = "|".join(
    re.escape(suffix)
    for suffix in sorted(
        {
            *_LOCATION_SUFFIXES_ZH,
            "桥头",
            "门口",
            "入口",
            "出口",
            "家",
            "家里",
            "家中",
            "室",
            "室内",
            "屋内",
            "屋外",
            "厅",
            "大厅",
            "房",
            "房内",
            "馆",
            "公司",
            "公寓",
            "旅馆",
            "酒吧",
            "教堂",
        },
        key=len,
        reverse=True,
    )
)
_AFFILIATION_SUFFIX_PATTERN_ZH = "|".join(
    re.escape(suffix)
    for suffix in sorted({*_AFFILIATION_SUFFIXES_ZH, "组织"}, key=len, reverse=True)
)
_ZH_LOCATION_VALUE_BODY = (
    rf"[^，。！？；：、“”‘’（）()\n]{{0,14}}(?:{_LOCATION_SUFFIX_PATTERN_ZH})(?:里|中|内|外|上|下)?"
)
_ZH_AFFILIATION_VALUE_BODY = (
    rf"[^，。！？；：、“”‘’（）()\n]{{0,12}}(?:{_AFFILIATION_SUFFIX_PATTERN_ZH})"
)
_EN_VALUE_TOKEN = r"[A-Z][A-Za-z0-9']*"
_EN_VALUE_CONNECTOR = r"(?:of|the|de|du|van|von)"
_EN_STRUCTURED_VALUE_BODY = (
    rf"{_EN_VALUE_TOKEN}(?:[ -](?:{_EN_VALUE_TOKEN}|{_EN_VALUE_CONNECTOR})){{0,5}}"
)
_CUE_CONTEXT_BREAKS = frozenset("，,。！？；：:、\n")
_LEADING_VALUE_PREFIXES = (
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
)
_DETERMINER_PREFIX_RE = re.compile(r"^(?:这|那|某|一)(?:座|间|条|处|个|所|片|家)")
_LATIN_VALUE_CONNECTORS = frozenset({"of", "the", "de", "du", "van", "von"})
_LIFE_STATE_PATTERNS_ZH: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("dead", ("死了", "已死", "身亡", "死亡", "殒命", "丧命"), 1.0),
    ("missing", ("失踪", "下落不明"), 1.0),
    ("incapacitated", ("昏迷", "重伤昏迷", "失去意识", "瘫倒"), 0.9),
    ("alive", ("还活着", "仍活着", "活着", "活了下来"), 1.0),
)
_LIFE_STATE_PATTERNS_EN: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("dead", ("is dead", "was killed", "died"), 1.0),
    ("missing", ("is missing", "went missing"), 1.0),
    ("incapacitated", ("is unconscious", "is incapacitated"), 0.9),
    ("alive", ("is alive", "stays alive"), 1.0),
)


@dataclass(frozen=True, slots=True)
class TargetSpec:
    id: str
    canonical_name: str
    kind: str = TARGET_KIND_ENTITY
    aliases: tuple[str, ...] = ()

    def all_aliases(self) -> tuple[str, ...]:
        ordered = [self.canonical_name, *self.aliases]
        deduped: list[str] = []
        seen: set[str] = set()
        for alias in ordered:
            normalized = (alias or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return tuple(deduped)


@dataclass(frozen=True, slots=True)
class ClaimKey:
    target_id: str
    slot: str


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: int
    chapter_id: int
    chapter_number: int
    start_pos: int
    end_pos: int
    progress_bucket: int
    prev_segment_id: int | None = None
    next_segment_id: int | None = None

    def to_compact(self) -> list[int | None]:
        return [
            self.segment_id,
            self.chapter_id,
            self.chapter_number,
            self.start_pos,
            self.end_pos,
            self.progress_bucket,
            self.prev_segment_id,
            self.next_segment_id,
        ]


@dataclass(frozen=True, slots=True)
class MentionPosting:
    target_id: str
    segment_id: int
    mention_score: float
    density: float
    best_anchor_offset: int

    def to_compact(self) -> list[str | int | float]:
        return [
            self.target_id,
            self.segment_id,
            round(self.mention_score, 4),
            round(self.density, 6),
            self.best_anchor_offset,
        ]


@dataclass(frozen=True, slots=True)
class ClaimAtom:
    claim_id: int
    key: ClaimKey
    value_signature: str
    segment_id: int
    chapter_number: int
    anchor_offset: int
    confidence: float
    cue_bitmap: int
    change_salience: float

    def to_compact(self) -> list[str | int | float]:
        return [
            self.claim_id,
            self.key.target_id,
            self.key.slot,
            self.value_signature,
            self.segment_id,
            self.chapter_number,
            self.anchor_offset,
            round(self.confidence, 4),
            self.cue_bitmap,
            round(self.change_salience, 4),
        ]


@dataclass(frozen=True, slots=True)
class CoverageRepresentative:
    target_id: str
    bucket_id: int
    segment_id: int
    rep_score: float

    def to_compact(self) -> list[str | int | float]:
        return [
            self.target_id,
            self.bucket_id,
            self.segment_id,
            round(self.rep_score, 4),
        ]


@dataclass(frozen=True, slots=True)
class Regime:
    key: ClaimKey
    value_signature: str
    claim_lo: int
    claim_hi: int
    start_segment_id: int
    end_segment_id: int
    support_score: float
    tail_support_score: float
    latest_support_segment_id: int
    rep_claim_ids: tuple[int, ...]
    conflict_after_score: float
    currentness_score: float
    has_asserted_support: bool


@dataclass(frozen=True, slots=True)
class CandidateStatePack:
    pack_id: str
    target_id: str
    slot: str
    candidate_value_signature: str
    support_score: float
    tail_support_score: float
    uncertainty_hint: str | None
    preview_excerpt: str
    primary_handle: str
    support_handle: str | None
    conflict_handle: str | None
    trace_handle: str | None
    source_handle: str


@dataclass(frozen=True, slots=True)
class SlotTraceRegimeRow:
    regime_handle: str
    value_signature: str
    chapter_from: int
    chapter_to: int
    support_score: float
    tail_support_score: float
    currentness_score: float
    is_current_candidate: bool


@dataclass(frozen=True, slots=True)
class SlotTracePack:
    trace_id: str
    target_id: str
    slot: str
    regimes: tuple[SlotTraceRegimeRow, ...]


@dataclass(frozen=True, slots=True)
class SourceOpenPayload:
    chapter_id: int
    chapter_number: int
    start_pos: int
    end_pos: int
    text: str
    prev_segment_handle: str | None = None
    next_segment_handle: str | None = None
    chapter_handle: str | None = None


@dataclass(frozen=True, slots=True)
class PackProvenance:
    pack: CandidateStatePack
    regime: Regime
    primary_claim: ClaimAtom
    segment: Segment
    source_payload: SourceOpenPayload


@dataclass(frozen=True, slots=True)
class StateProtoChapterShard:
    chapter_id: int
    chapter_number: int
    source_signature: str | None
    segments: tuple[Segment, ...]
    mention_postings: tuple[MentionPosting, ...]
    claim_atoms: tuple[ClaimAtom, ...]


@dataclass(frozen=True, slots=True)
class StateProtoArtifacts:
    language: str
    targets: tuple[TargetSpec, ...]
    index: "StateProtoIndex"
    segment_count: int
    mention_posting_count: int
    claim_atom_count: int
    coverage_rep_count: int
    chapter_shards: tuple[StateProtoChapterShard, ...] = ()
    segmentation_ms: float = 0.0
    discover_targets_ms: float = 0.0
    mention_ms: float = 0.0
    claim_ms: float = 0.0
    coverage_ms: float = 0.0


@dataclass(slots=True)
class StateProtoBuildOutput:
    asset_state: str
    executor_backend: str = STATE_PROTO_EXECUTOR_BACKEND_NONE
    index_payload: bytes | None = None
    chapter_count: int = 0
    chapter_chars: int = 0
    load_chapters_ms: float = 0.0
    target_count: int = 0
    segment_count: int = 0
    mention_posting_count: int = 0
    claim_atom_count: int = 0
    coverage_rep_count: int = 0
    segmentation_ms: float = 0.0
    discover_targets_ms: float = 0.0
    mention_ms: float = 0.0
    claim_ms: float = 0.0
    coverage_ms: float = 0.0
    serialize_ms: float = 0.0
    duration_ms: float = 0.0
    payload_bytes: int = 0
    rss_kib: int | None = None
    peak_rss_kib: int | None = None
    plan_mode: str = "full"
    incremental_applied: bool = False
    rebuilt_chapter_count: int = 0
    reused_chapter_count: int = 0
    fallback_reason: str | None = None

def _normalize_chapter_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized)
    return normalized.strip()


def compute_state_proto_chapter_signature(text: str) -> str:
    normalized = _normalize_chapter_text(text)
    return blake2s(normalized.encode("utf-8"), digest_size=16).hexdigest()
