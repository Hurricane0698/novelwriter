export interface Novel {
  id: number
  title: string
  author: string
  total_chapters: number
  created_at: string
  updated_at: string
}

export interface ChapterMeta {
  id: number
  novel_id: number
  chapter_number: number
  title: string
  created_at: string
}

export interface Chapter {
  id: number
  novel_id: number
  chapter_number: number
  title: string
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
  temperature?: number
}

export interface PostcheckWarning {
  code: string
  term: string
  message: string
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
  postcheck_warnings: PostcheckWarning[]
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
export type SystemDisplayType = 'hierarchy' | 'graph' | 'timeline' | 'list'
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
  display_type: SystemDisplayType
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

export interface UserPreferences {
  num_versions?: number
  temperature?: number
  context_chapters?: number
  target_chars?: number
}

export type StreamEvent =
  | { type: 'start'; variant: number; total_variants: number; debug?: ContinueDebugSummary | null }
  | { type: 'token'; variant: number; content: string }
  | { type: 'variant_done'; variant: number; continuation_id: number; content: string }
  | { type: 'done'; continuation_ids: number[]; debug?: ContinueDebugSummary }
  | { type: 'error'; message: string; code?: string; request_id?: string; variant?: number }
