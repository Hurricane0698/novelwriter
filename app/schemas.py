from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, TypeAdapter
from pydantic_core import PydanticCustomError
from typing import ClassVar, Optional, List, Literal, Any
from datetime import datetime
from enum import Enum

from app.config import MAX_CONTEXT_CHAPTERS
from app.world_visibility import WorldVisibility, normalize_visibility

WorldOrigin = Literal["manual", "bootstrap", "worldpack", "worldgen"]
SystemDisplayType = Literal["hierarchy", "graph", "timeline", "list"]


class NovelBase(BaseModel):
    title: str
    author: str = ""


class NovelCreate(NovelBase):
    pass


class NovelResponse(NovelBase):
    id: int
    total_chapters: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChapterResponse(BaseModel):
    id: int
    novel_id: int
    chapter_number: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChapterMetaResponse(BaseModel):
    id: int
    novel_id: int
    chapter_number: int
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChapterUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None


class ChapterCreateRequest(BaseModel):
    chapter_number: int | None = None  # default: smallest missing positive chapter number
    title: str = ""
    content: str = ""


class OutlineResponse(BaseModel):
    id: int
    novel_id: int
    chapter_start: int
    chapter_end: int
    outline_text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContinuationResponse(BaseModel):
    id: int
    novel_id: int
    chapter_number: int
    content: str
    rating: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContinueRequest(BaseModel):
    ALLOWED_TARGET_CHARS: ClassVar[set[int]] = {2000, 3000, 5000}

    num_versions: int = Field(default=1, ge=1, le=2)
    prompt: str | None = Field(default=None, max_length=2000, description="用户续写指令")
    max_tokens: int | None = Field(default=None, ge=100, le=16000, description="生成的最大 token 数")
    target_chars: int | None = Field(default=None, description="目标续写字数（2000/3000/5000）")
    context_chapters: int | None = Field(
        default=None,
        ge=1,
        description=f"用于续写上下文的最近章节数（仅允许 1-{MAX_CONTEXT_CHAPTERS}，超过时按 {MAX_CONTEXT_CHAPTERS} 处理）",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="LLM 采样温度（0.0-2.0），默认 0.8",
    )

    @model_validator(mode="after")
    def _validate_target_chars(self):
        if self.target_chars is not None and self.target_chars not in self.ALLOWED_TARGET_CHARS:
            raise ValueError(f"target_chars must be one of {sorted(self.ALLOWED_TARGET_CHARS)}")
        if self.context_chapters is not None and self.context_chapters > MAX_CONTEXT_CHAPTERS:
            self.context_chapters = MAX_CONTEXT_CHAPTERS
        return self


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


class UploadResponse(BaseModel):
    novel_id: int
    total_chapters: int
    message: str


class OutlineGenerateResponse(BaseModel):
    outlines: List[OutlineResponse]


class PostcheckWarning(BaseModel):
    """Post-generation consistency/lore drift warning (non-blocking)."""

    code: str
    term: str
    message: str
    version: int | None = None
    evidence: str | None = None


class ContinueDebugSummary(BaseModel):
    """Debug summary for context injection (WorldModel)."""

    context_chapters: int
    injected_systems: List[str] = Field(default_factory=list)
    injected_entities: List[str] = Field(default_factory=list)
    injected_relationships: List[str] = Field(default_factory=list)
    relevant_entity_ids: List[int] = Field(default_factory=list)
    ambiguous_keywords_disabled: List[str] = Field(default_factory=list)
    postcheck_warnings: List[PostcheckWarning] = Field(default_factory=list)


class ContinueResponse(BaseModel):
    continuations: List[ContinuationResponse]
    debug: ContinueDebugSummary


class ErrorResponse(BaseModel):
    detail: str


# Lorebook Schemas

class LoreEntryType(str, Enum):
    CHARACTER = "Character"
    LOCATION = "Location"
    ITEM = "Item"
    FACTION = "Faction"
    EVENT = "Event"


class LoreKeyCreate(BaseModel):
    keyword: str
    is_regex: bool = False
    case_sensitive: bool = True


class LoreKeyResponse(BaseModel):
    id: int
    keyword: str
    is_regex: bool
    case_sensitive: bool

    model_config = ConfigDict(from_attributes=True)


class LoreEntryCreate(BaseModel):
    title: str
    content: str
    entry_type: LoreEntryType
    token_budget: int = Field(default=500, ge=50, le=2000)
    priority: int = Field(default=100, ge=1, le=1000)
    keywords: List[LoreKeyCreate]


class LoreEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    entry_type: Optional[LoreEntryType] = None
    token_budget: Optional[int] = Field(default=None, ge=50, le=2000)
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
    enabled: Optional[bool] = None


class LoreEntryResponse(BaseModel):
    id: int
    novel_id: int
    uid: str
    title: str
    content: str
    entry_type: str
    token_budget: int
    priority: int
    enabled: bool
    keywords: List[LoreKeyResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoreMatchResult(BaseModel):
    entry_id: int
    title: str
    content: str
    entry_type: str
    priority: int
    matched_keywords: List[str]
    tokens_used: int


class LoreInjectionResponse(BaseModel):
    context: str
    matched_entries: List[LoreMatchResult]
    total_tokens: int


# Rollback Schemas

class RollbackResponse(BaseModel):
    """Response for rollback operation."""
    novel_id: int
    rolled_back_to_chapter: int
    message: str


# =============================================================================
# Aggregation API Schemas (Frontend-friendly)
# =============================================================================

class ComponentStatus(BaseModel):
    """Status of a single component."""
    ready: bool
    count: Optional[int] = None
    details: Optional[str] = None


class OrchestrationStatusSummary(BaseModel):
    """Summary of orchestration component status."""
    lorebook: ComponentStatus


class RecentChapterSummary(BaseModel):
    """Summary of a recent chapter."""
    chapter_number: int
    title: str
    char_count: int


class NovelDashboard(BaseModel):
    """Aggregated dashboard data for a novel."""
    # Basic info
    novel_id: int
    title: str
    author: str
    total_chapters: int

    # Component status
    status: OrchestrationStatusSummary

    # Recent chapters
    recent_chapters: List[RecentChapterSummary] = Field(default_factory=list)


# Batch operation schemas

class LoreEntryBatchCreate(BaseModel):
    """Batch create lorebook entries."""
    entries: List[LoreEntryCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of entries to create (max 100)"
    )


class LoreEntryBatchResponse(BaseModel):
    """Response for batch lorebook creation."""
    created: int
    entries: List[LoreEntryResponse]
    errors: List[str] = Field(default_factory=list)


# =============================================================================
# World Model Schemas
# =============================================================================

class WorldEntityCreate(BaseModel):
    name: str = Field(max_length=255)
    entity_type: str = Field(max_length=50)
    description: str = ""
    aliases: List[str] = Field(default_factory=list)


class WorldEntityUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    entity_type: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = None
    aliases: Optional[List[str]] = None


class WorldEntityAttributeResponse(BaseModel):
    id: int
    entity_id: int
    key: str
    surface: str
    truth: Optional[str] = None
    visibility: str
    origin: WorldOrigin
    worldpack_pack_id: str | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorldEntityResponse(BaseModel):
    id: int
    novel_id: int
    name: str
    entity_type: str
    description: str
    aliases: List[str]
    origin: WorldOrigin
    worldpack_pack_id: str | None = None
    worldpack_key: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorldEntityDetailResponse(WorldEntityResponse):
    attributes: List[WorldEntityAttributeResponse] = Field(default_factory=list)


class WorldAttributeCreate(BaseModel):
    key: str = Field(max_length=255)
    surface: str
    truth: Optional[str] = None
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class WorldAttributeUpdate(BaseModel):
    key: Optional[str] = Field(default=None, max_length=255)
    surface: Optional[str] = None
    truth: Optional[str] = None
    visibility: Optional[WorldVisibility] = None

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        if v is None:
            return v
        return normalize_visibility(v)


class AttributeReorderRequest(BaseModel):
    order: List[int]


class BatchConfirmRequest(BaseModel):
    ids: List[int]


class BatchConfirmResponse(BaseModel):
    confirmed: int


class BatchRejectRequest(BaseModel):
    ids: List[int]


class BatchRejectResponse(BaseModel):
    rejected: int


class WorldRelationshipCreate(BaseModel):
    source_id: int
    target_id: int
    label: str = Field(max_length=100)
    description: str = ""
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class WorldRelationshipUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    visibility: Optional[WorldVisibility] = None

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        if v is None:
            return v
        return normalize_visibility(v)


class WorldRelationshipResponse(BaseModel):
    id: int
    novel_id: int
    source_id: int
    target_id: int
    label: str
    description: str
    visibility: str
    origin: WorldOrigin
    worldpack_pack_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# WorldSystem data validation (per world-model-schema.md)
# ---------------------------------------------------------------------------


class _HierarchyNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=255)
    label: str
    entity_id: int | None = None
    visibility: WorldVisibility = "active"
    children: List["_HierarchyNode"] = Field(default_factory=list)

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


_HierarchyNode.model_rebuild()


class _HierarchyData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: List[_HierarchyNode] = Field(default_factory=list)


class _GraphPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Preserve integer JSON values (e.g. {"x": 0}) for contract roundtrips while
    # still accepting floats.
    x: int | float
    y: int | float


class _GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=255)
    label: str
    entity_id: int | None = None
    position: _GraphPosition
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class _GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from", min_length=1, max_length=255)
    to: str = Field(min_length=1, max_length=255)
    label: str
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class _GraphData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: List[_GraphNode] = Field(default_factory=list)
    edges: List[_GraphEdge] = Field(default_factory=list)


class _TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str
    label: str
    description: str | None = None
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class _TimelineData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: List[_TimelineEvent] = Field(default_factory=list)


class _ListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional stable key for list items (commonly provided by worldpack imports).
    # If present, we preserve it through validation and roundtrip.
    id: str | None = Field(default=None, min_length=1, max_length=255)
    label: str
    description: str | None = None
    visibility: WorldVisibility = "active"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class _ListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[_ListItem] = Field(default_factory=list)


_SYSTEM_DATA_ADAPTERS: dict[SystemDisplayType, TypeAdapter] = {
    "hierarchy": TypeAdapter(_HierarchyData),
    "graph": TypeAdapter(_GraphData),
    "timeline": TypeAdapter(_TimelineData),
    "list": TypeAdapter(_ListData),
}


def _normalize_and_validate_system_data(display_type: SystemDisplayType, data: Any) -> dict:
    adapter = _SYSTEM_DATA_ADAPTERS.get(display_type)
    if adapter is None:
        # Defensive: DB rows may contain legacy/invalid display_type values.
        # Prefer a clean validation error over KeyError -> 500.
        raise ValueError(f"Unknown system display_type: {display_type}")
    parsed = adapter.validate_python(data if data is not None else {})
    # Preserve the canonical wire keys (e.g. "from" for graph edges).
    # Do not inject defaults into user payloads; contract tests expect exact
    # roundtrip semantics for system.data.
    return parsed.model_dump(by_alias=True, exclude_unset=True)


class WorldSystemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    display_type: SystemDisplayType
    description: str = ""
    data: dict = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_data(self) -> "WorldSystemCreate":
        self.data = _normalize_and_validate_system_data(self.display_type, self.data)
        return self


class WorldSystemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=255)
    display_type: Optional[SystemDisplayType] = None
    description: Optional[str] = None
    data: Optional[dict] = None
    constraints: Optional[List[str]] = None
    visibility: Optional[WorldVisibility] = None

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        if v is None:
            return v
        return normalize_visibility(v)


class WorldSystemResponse(BaseModel):
    id: int
    novel_id: int
    name: str
    display_type: SystemDisplayType
    description: str
    data: dict
    constraints: List[str]
    visibility: str
    origin: WorldOrigin
    worldpack_pack_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BootstrapStatus(str, Enum):
    PENDING = "pending"
    TOKENIZING = "tokenizing"
    EXTRACTING = "extracting"
    WINDOWING = "windowing"
    REFINING = "refining"
    COMPLETED = "completed"
    FAILED = "failed"


class BootstrapMode(str, Enum):
    INITIAL = "initial"
    INDEX_REFRESH = "index_refresh"
    REEXTRACT = "reextract"


class BootstrapDraftPolicy(str, Enum):
    REPLACE_BOOTSTRAP_DRAFTS = "replace_bootstrap_drafts"
    MERGE = "merge"


class BootstrapTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: BootstrapMode = BootstrapMode.INDEX_REFRESH
    draft_policy: Optional[BootstrapDraftPolicy] = None
    force: bool = False


class BootstrapProgress(BaseModel):
    step: int = 0
    detail: str = ""


class BootstrapResult(BaseModel):
    entities_found: int = 0
    relationships_found: int = 0
    index_refresh_only: bool = False


class BootstrapJobResponse(BaseModel):
    job_id: int
    novel_id: int
    mode: BootstrapMode = BootstrapMode.INDEX_REFRESH
    initialized: bool = False
    status: BootstrapStatus
    progress: BootstrapProgress
    result: BootstrapResult
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# =============================================================================
# World Generation (LLM -> Drafts)
# =============================================================================


class WorldGenerateRequest(BaseModel):
    """Generate world model drafts from free text (world settings)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=10, max_length=50_000)

    @field_validator("text")
    @classmethod
    def _reject_whitespace_only(cls, v: str) -> str:
        # Pydantic's min_length counts whitespace; user intent does not.
        non_ws_len = sum(1 for ch in (v or "") if not ch.isspace())
        if non_ws_len < 10:
            raise PydanticCustomError(
                "world_generate_text_too_short_non_whitespace",
                "text must be at least {min} non-whitespace characters",
                {"min": 10, "non_whitespace_len": non_ws_len},
            )
        return v


class WorldGenerateWarning(BaseModel):
    code: str
    message: str
    path: str | None = None


class WorldGenerateResponse(BaseModel):
    entities_created: int = 0
    relationships_created: int = 0
    systems_created: int = 0
    warnings: List[WorldGenerateWarning] = Field(default_factory=list)


# =============================================================================
# Worldpack Schemas
# =============================================================================


class WorldpackV1Source(BaseModel):
    """Minimal source attribution info for worldpack.v1."""

    model_config = ConfigDict(extra="forbid")
    wiki_base_url: str = Field(max_length=2048)


class WorldpackV1Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=255)
    surface: str
    truth: str | None = None
    visibility: WorldVisibility = "reference"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class WorldpackV1Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    entity_type: str = Field(min_length=1, max_length=50)
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    attributes: List[WorldpackV1Attribute] = Field(default_factory=list)


class WorldpackV1Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(min_length=1, max_length=255)
    target_key: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=100)
    description: str = ""
    visibility: WorldVisibility = "reference"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)


class WorldpackV1System(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    display_type: SystemDisplayType
    description: str = ""
    data: dict = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    visibility: WorldVisibility = "reference"

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility_field(cls, v: object) -> object:
        return normalize_visibility(v)

    @model_validator(mode="after")
    def _validate_data(self) -> "WorldpackV1System":
        self.data = _normalize_and_validate_system_data(self.display_type, self.data)
        return self


class WorldpackV1Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    pack_id: str = Field(min_length=1, max_length=255)
    pack_name: str = Field(min_length=1, max_length=255)
    language: str = Field(min_length=1, max_length=50)
    license: str
    source: WorldpackV1Source
    generated_at: datetime

    entities: List[WorldpackV1Entity] = Field(default_factory=list)
    relationships: List[WorldpackV1Relationship] = Field(default_factory=list)
    systems: List[WorldpackV1System] = Field(default_factory=list)


class WorldpackImportCounts(BaseModel):
    entities_created: int = 0
    entities_updated: int = 0
    entities_deleted: int = 0

    attributes_created: int = 0
    attributes_updated: int = 0
    attributes_deleted: int = 0

    relationships_created: int = 0
    relationships_updated: int = 0
    relationships_deleted: int = 0

    systems_created: int = 0
    systems_updated: int = 0
    systems_deleted: int = 0


class WorldpackImportWarning(BaseModel):
    code: str
    message: str
    path: str | None = None


class WorldpackImportResponse(BaseModel):
    pack_id: str
    counts: WorldpackImportCounts
    warnings: List[WorldpackImportWarning] = Field(default_factory=list)
