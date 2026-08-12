export type NovelContentFormat = 'plain_text' | 'markdown'

export interface Novel {
  id: number
  title: string
  author: string
  language: string
  content_format: NovelContentFormat
  total_chapters: number
  is_seeded_demo?: boolean
  window_index?: WindowIndexState
  created_at: string
  updated_at: string
}

export type WindowIndexLifecycleStatus = 'missing' | 'stale' | 'fresh' | 'failed'
export type DerivedAssetJobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type NovelIngestJobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type NovelIngestJobStage =
  | 'accepted'
  | 'decoding'
  | 'parsing'
  | 'persisting'
  | 'planning'
  | 'completed'
  | 'failed'
export type NovelIngestErrorCode =
  | 'source_missing'
  | 'source_encoding_unsupported'
  | 'markdown_structure_invalid'
  | 'ingest_internal_error'
export type NovelIngestSizeTier = 'normal' | 'large' | 'xlarge' | 'reject'
export type WindowIndexReadinessStatus =
  | 'accepting'
  | 'processing'
  | 'ready'
  | 'degraded_ready'
  | 'failed_retryable'
  | 'failed_terminal'

export interface WindowIndexJobMetrics {
  queue_wait_ms: number | null
  load_chapters_ms: number | null
  build_artifacts_ms: number | null
  serialize_ms: number | null
  persist_ms: number | null
  full_build_ms: number | null
  chapter_count: number | null
  chapter_chars: number | null
  payload_bytes: number | null
  rss_kib: number | null
  peak_rss_kib: number | null
  index_backend: string | null
  executor_backend: string | null
  target_count: number | null
  segment_count: number | null
  mention_posting_count: number | null
  claim_atom_count: number | null
  coverage_rep_count: number | null
  discover_targets_ms: number | null
  segmentation_ms: number | null
  mention_ms: number | null
  claim_ms: number | null
  coverage_ms: number | null
  plan_mode: string | null
  incremental_applied: boolean | null
  rebuilt_chapter_count: number | null
  reused_chapter_count: number | null
  fallback_reason: string | null
}

export interface WindowIndexJob {
  status: DerivedAssetJobStatus
  target_revision: number
  completed_revision: number | null
  error: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  metrics: WindowIndexJobMetrics | null
}

export interface NovelIngestJob {
  status: NovelIngestJobStatus
  stage: NovelIngestJobStage
  size_tier: NovelIngestSizeTier | null
  source_bytes: number
  source_chars: number | null
  chapter_count: number | null
  requested_language: string | null
  resolved_language: string | null
  auto_index_plan: string | null
  bootstrap_plan: string | null
  readiness_mode: string | null
  error_code: NovelIngestErrorCode | null
  error: string | null
}

export interface WindowIndexCapabilities {
  chapters_available: boolean
  whole_book_index_available: boolean
  bootstrap_available: boolean
  recent_fallback_only: boolean
}

export interface WindowIndexState {
  status: WindowIndexLifecycleStatus
  revision: number
  built_revision: number | null
  error: string | null
  readiness: WindowIndexReadinessStatus
  capabilities: WindowIndexCapabilities
  ingest?: NovelIngestJob | null
  job: WindowIndexJob | null
}

export interface ChapterMeta {
  id: number
  novel_id: number
  chapter_number: number
  title: string
  source_chapter_label: string | null
  source_chapter_number: number | null
  source_volume_title: string | null
  created_at: string
}

export interface Chapter {
  id: number
  novel_id: number
  chapter_number: number
  title: string
  source_chapter_label: string | null
  source_chapter_number: number | null
  source_volume_title: string | null
  content: string
  created_at: string
  updated_at: string | null
}

export interface ChapterCreateRequest {
  chapter_number?: number
  title?: string
  content?: string
}

export interface ChapterUpdateRequest {
  title?: string
  content?: string
}

export interface ContinueRequest {
  num_versions?: number
  prompt?: string
  max_tokens?: number
  target_chars?: number
  context_chapters?: number
  outline_ids?: number[]
  temperature?: number
}

export interface NovelOutline {
  id: number
  novel_id: number
  start_chapter: number
  end_chapter: number
  title: string
  content: string
  model?: string | null
  created_at: string
  updated_at: string
}

export interface PostcheckWarning {
  code: string
  term: string
  message: string
  message_key: string
  message_params: Record<string, string | number | boolean | null>
  version: number | null
  evidence: string | null
}

export interface ProseWarning {
  code: string
  message: string
  message_key: string
  message_params: Record<string, string | number | boolean | null>
  version: number | null
  evidence: string | null
}

export interface ContinueDebugSummary {
  context_chapters: number
  injected_systems: string[]
  injected_entities: string[]
  injected_relationships: string[]
  relevant_entity_ids: number[]
  ambiguous_keywords_disabled: string[]
  drift_warnings: PostcheckWarning[]
  prose_warnings: ProseWarning[]
}

export interface Continuation {
  id: number
  novel_id: number
  chapter_number: number
  content: string
  rating: number | null
  created_at: string
}

export interface ContinueResponse {
  continuations: Continuation[]
  debug: ContinueDebugSummary
}

// World Model Types
export type Visibility = 'active' | 'reference' | 'hidden'
export type EntityStatus = 'draft' | 'confirmed'
export type SystemDisplayType = 'hierarchy' | 'timeline' | 'list'
export type LegacySystemDisplayType = SystemDisplayType | 'graph'
export type WorldOrigin = 'manual' | 'bootstrap' | 'worldpack' | 'worldgen'

export interface WorldEntity {
  id: number
  novel_id: number
  name: string
  entity_type: string
  description: string
  aliases: string[]
  origin: WorldOrigin
  worldpack_pack_id: string | null
  worldpack_key: string | null
  status: EntityStatus
  created_at: string
  updated_at: string
}

export interface WorldEntityAttribute {
  id: number
  entity_id: number
  key: string
  surface: string
  truth: string | null
  visibility: Visibility
  origin: WorldOrigin
  worldpack_pack_id: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface WorldEntityDetail extends WorldEntity {
  attributes: WorldEntityAttribute[]
}

export interface WorldRelationship {
  id: number
  novel_id: number
  source_id: number
  target_id: number
  label: string
  description: string
  visibility: Visibility
  origin: WorldOrigin
  worldpack_pack_id: string | null
  status: EntityStatus
  created_at: string
  updated_at: string
}

export interface WorldSystem {
  id: number
  novel_id: number
  name: string
  display_type: LegacySystemDisplayType
  description: string
  data: Record<string, unknown>
  constraints: string[]
  visibility: Visibility
  origin: WorldOrigin
  worldpack_pack_id: string | null
  status: EntityStatus
  created_at: string
  updated_at: string
}

export interface WorldGenerateRequest {
  text: string
}

export interface WorldGenerateWarning {
  code: string
  message: string
  message_key: string
  message_params: Record<string, string | number | boolean | null>
  path?: string | null
}

export interface WorldGenerateResponse {
  entities_created: number
  relationships_created: number
  systems_created: number
  warnings: WorldGenerateWarning[]
}

export interface CreateEntityRequest {
  name: string
  entity_type: string
  description?: string
  aliases?: string[]
}

export interface UpdateEntityRequest {
  name?: string
  entity_type?: string
  description?: string
  aliases?: string[]
}

export interface CreateAttributeRequest {
  key: string
  surface: string
  truth?: string
  visibility?: Visibility
}

export interface UpdateAttributeRequest {
  key?: string
  surface?: string
  truth?: string | null
  visibility?: Visibility
}

export interface CreateRelationshipRequest {
  source_id: number
  target_id: number
  label: string
  description?: string
  visibility?: Visibility
}

export interface UpdateRelationshipRequest {
  label?: string
  description?: string
  visibility?: Visibility
}

export interface CreateSystemRequest {
  name: string
  display_type: SystemDisplayType
  description?: string
  data?: Record<string, unknown>
  constraints?: string[]
}

export interface UpdateSystemRequest {
  name?: string
  display_type?: SystemDisplayType
  description?: string
  data?: Record<string, unknown>
  constraints?: string[]
  visibility?: Visibility
}

export interface BatchConfirmResponse {
  confirmed: number
}

export type BootstrapStatus = 'pending' | 'tokenizing' | 'extracting' | 'windowing' | 'refining' | 'completed' | 'failed'
export type BootstrapMode = 'initial' | 'index_refresh' | 'reextract'
export type BootstrapDraftPolicy = 'replace_bootstrap_drafts' | 'merge'

export interface BootstrapTriggerRequest {
  mode: BootstrapMode
  draft_policy?: BootstrapDraftPolicy
  force?: boolean
}

export interface BootstrapProgress {
  step: number
  detail: string
}

export interface BootstrapResult {
  entities_found: number
  relationships_found: number
  index_refresh_only: boolean
}

export interface BootstrapJobResponse {
  job_id: number
  novel_id: number
  mode: BootstrapMode
  initialized: boolean
  status: BootstrapStatus
  progress: BootstrapProgress
  result: BootstrapResult
  error: string | null
  created_at: string
  updated_at: string
}

export interface WorldpackV1 {
  schema_version: 'worldpack.v1'
  pack_id?: string
  pack_name?: string
  language?: string
  generated_at?: string
  entities?: unknown[]
  relationships?: unknown[]
  systems?: unknown[]
  [key: string]: unknown
}

export interface WorldpackImportCounts {
  entities_created: number
  entities_updated: number
  entities_deleted: number
  attributes_created: number
  attributes_updated: number
  attributes_deleted: number
  relationships_created: number
  relationships_updated: number
  relationships_deleted: number
  systems_created: number
  systems_updated: number
  systems_deleted: number
}

export interface WorldpackImportWarning {
  code: string
  message: string
  message_key: string
  message_params: Record<string, string | number | boolean | null>
  path?: string | null
}

export interface WorldpackImportResponse {
  pack_id: string
  counts: WorldpackImportCounts
  warnings: WorldpackImportWarning[]
}

// Auth types
export interface QuotaResponse {
  generation_quota: number
  feedback_submitted: boolean
}

export type StreamEvent =
  | { type: 'start'; variant: number; total_variants: number; debug?: ContinueDebugSummary | null }
  | { type: 'token'; variant: number; content: string }
  | { type: 'variant_done'; variant: number; continuation_id: number; content: string }
  | { type: 'done'; continuation_ids: number[]; debug?: ContinueDebugSummary }
  | { type: 'error'; message: string; code?: string; request_id?: string; variant?: number }
