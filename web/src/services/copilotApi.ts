import type {
  CopilotContextData,
  CopilotContextStage,
  CopilotContextSurface,
  CopilotContextTab,
  CopilotEvidence,
  CopilotFieldDelta,
  CopilotMode,
  CopilotReviewKind,
  CopilotRun,
  CopilotRunStatus,
  CopilotScope,
  CopilotSuggestion,
  CopilotSuggestionApplyAction,
  CopilotSuggestionPreview,
  CopilotSuggestionTarget,
  CopilotTargetTab,
  CopilotTraceStep,
} from '@/types/copilot'
import { llmHeaders, request, requestParsed } from './apiClient'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function invalidResponseShape(message: string): never {
  throw new Error(`Invalid API response shape: ${message}`)
}

function expectRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) invalidResponseShape(label)
  return value
}

function expectString(value: unknown, label: string): string {
  if (typeof value !== 'string') invalidResponseShape(label)
  return value
}

function readOptionalString(value: unknown): string | null | undefined {
  if (value == null) return value as null | undefined
  return typeof value === 'string' ? value : invalidResponseShape('optional string')
}

function expectBoolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') invalidResponseShape(label)
  return value
}

function readOptionalNumber(value: unknown, label: string): number | null | undefined {
  if (value == null) return value as null | undefined
  if (typeof value !== 'number' || !Number.isFinite(value)) invalidResponseShape(label)
  return value
}

function expectArray(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) invalidResponseShape(label)
  return value
}

function expectStringArray(value: unknown, label: string): string[] {
  return expectArray(value, label).map((item, index) => expectString(item, `${label}[${index}]`))
}

function expectEnumValue<T extends string>(
  value: unknown,
  allowed: readonly T[],
  label: string,
): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) invalidResponseShape(label)
  return value as T
}

const COPILOT_CONTEXT_STAGES = ['chapter', 'write', 'results', 'entity', 'relationship', 'system', 'review'] as const
const COPILOT_RUN_STATUSES = ['idle', 'queued', 'running', 'completed', 'error', 'interrupted'] as const
const COPILOT_SUGGESTION_STATUSES = ['pending', 'applied', 'dismissed'] as const
const COPILOT_TARGET_TABS = ['entities', 'relationships', 'systems', 'review'] as const
const COPILOT_REVIEW_KINDS = ['entities', 'relationships', 'systems'] as const
const COPILOT_SUGGESTION_RESOURCES = ['entity', 'relationship', 'system'] as const
const COPILOT_CONTEXT_TABS = ['entities', 'relationships', 'review', 'systems'] as const
const COPILOT_CONTEXT_SURFACES = ['studio', 'atlas'] as const
const COPILOT_MODES = ['research', 'current_entity', 'draft_cleanup'] as const
const COPILOT_SCOPES = ['whole_book', 'current_entity', 'current_tab'] as const
const COPILOT_APPLY_TYPES = [
  'create_entity',
  'update_entity',
  'create_relationship',
  'update_relationship',
  'create_system',
  'update_system',
] as const

function parseCopilotContextData(value: unknown): CopilotContextData | null {
  if (value == null) return null
  const body = expectRecord(value, 'copilot context')
  const entityId = readOptionalNumber(body.entity_id, 'copilot context.entity_id')
  const surface = body.surface == null
    ? undefined
    : expectEnumValue(body.surface, COPILOT_CONTEXT_SURFACES, 'copilot context.surface')
  const rawStage = readOptionalString(body.stage)
  const tab = body.tab == null
    ? undefined
    : expectEnumValue(body.tab, COPILOT_CONTEXT_TABS, 'copilot context.tab')
  if (surface === 'atlas' && tab == null) invalidResponseShape('copilot context.tab')
  const stage = rawStage == null || surface === 'atlas'
    ? undefined
    : expectEnumValue(rawStage, COPILOT_CONTEXT_STAGES, 'copilot context.stage')
  return {
    entity_id: entityId ?? undefined,
    tab: tab as CopilotContextTab | undefined,
    surface: surface as CopilotContextSurface | undefined,
    stage: stage as CopilotContextStage | undefined,
  }
}

function parseCopilotTraceStep(value: unknown): CopilotTraceStep {
  const body = expectRecord(value, 'copilot trace step')
  return {
    step_id: expectString(body.step_id, 'copilot trace step.step_id'),
    kind: expectString(body.kind, 'copilot trace step.kind'),
    status: expectString(body.status, 'copilot trace step.status'),
    summary: expectString(body.summary, 'copilot trace step.summary'),
  }
}

function parseCopilotEvidence(value: unknown): CopilotEvidence {
  const body = expectRecord(value, 'copilot evidence')
  const sourceRef = body.source_ref == null ? null : expectRecord(body.source_ref, 'copilot evidence.source_ref')
  const sourceRefs = body.source_refs == null
    ? []
    : expectArray(body.source_refs, 'copilot evidence.source_refs').map((item) => expectRecord(item, 'copilot evidence.source_refs[]'))
  const anchorTerms = body.anchor_terms == null
    ? []
    : expectArray(body.anchor_terms, 'copilot evidence.anchor_terms').map((item) => expectString(item, 'copilot evidence.anchor_terms[]'))
  return {
    evidence_id: expectString(body.evidence_id, 'copilot evidence.evidence_id'),
    source_type: expectString(body.source_type, 'copilot evidence.source_type'),
    source_ref: sourceRef,
    title: expectString(body.title, 'copilot evidence.title'),
    excerpt: expectString(body.excerpt, 'copilot evidence.excerpt'),
    why_relevant: expectString(body.why_relevant, 'copilot evidence.why_relevant'),
    pack_id: readOptionalString(body.pack_id) ?? null,
    source_refs: sourceRefs,
    anchor_terms: anchorTerms,
    support_count: readOptionalNumber(body.support_count, 'copilot evidence.support_count') ?? null,
    preview_excerpt: readOptionalString(body.preview_excerpt) ?? null,
    expanded: body.expanded == null ? false : expectBoolean(body.expanded, 'copilot evidence.expanded'),
  }
}

function parseCopilotFieldDelta(value: unknown): CopilotFieldDelta {
  const body = expectRecord(value, 'copilot field delta')
  return {
    field: expectString(body.field, 'copilot field delta.field'),
    label: expectString(body.label, 'copilot field delta.label'),
    before: readOptionalString(body.before) ?? null,
    after: expectString(body.after, 'copilot field delta.after'),
  }
}

function parseCopilotSuggestionTarget(value: unknown): CopilotSuggestionTarget {
  const body = expectRecord(value, 'copilot suggestion target')
  const resource = expectEnumValue(body.resource, COPILOT_SUGGESTION_RESOURCES, 'copilot suggestion target.resource')
  const tab = expectEnumValue(body.tab, COPILOT_TARGET_TABS, 'copilot suggestion target.tab')
  const reviewKind = body.review_kind == null
    ? undefined
    : expectEnumValue(body.review_kind, COPILOT_REVIEW_KINDS, 'copilot suggestion target.review_kind')
  const entityId = readOptionalNumber(body.entity_id, 'copilot suggestion target.entity_id')
  const highlightId = readOptionalNumber(body.highlight_id, 'copilot suggestion target.highlight_id')

  return {
    resource,
    resource_id: readOptionalNumber(body.resource_id, 'copilot suggestion target.resource_id') ?? null,
    label: expectString(body.label, 'copilot suggestion target.label'),
    tab: tab as CopilotTargetTab,
    entity_id: entityId == null ? undefined : entityId,
    review_kind: reviewKind as CopilotReviewKind | undefined,
    highlight_id: highlightId == null ? undefined : highlightId,
  }
}

function parseCopilotSuggestionPreview(value: unknown): CopilotSuggestionPreview {
  const body = expectRecord(value, 'copilot suggestion preview')
  return {
    target_label: expectString(body.target_label, 'copilot suggestion preview.target_label'),
    summary: expectString(body.summary, 'copilot suggestion preview.summary'),
    field_deltas: expectArray(body.field_deltas ?? [], 'copilot suggestion preview.field_deltas')
      .map(parseCopilotFieldDelta),
    evidence_quotes: expectStringArray(body.evidence_quotes ?? [], 'copilot suggestion preview.evidence_quotes'),
    actionable: expectBoolean(body.actionable, 'copilot suggestion preview.actionable'),
    non_actionable_reason: readOptionalString(body.non_actionable_reason) ?? null,
  }
}

function parseCopilotSuggestionApplyAction(value: unknown): CopilotSuggestionApplyAction | null {
  if (value == null) return null
  const body = expectRecord(value, 'copilot suggestion apply action')
  const type = expectEnumValue(body.type, COPILOT_APPLY_TYPES, 'copilot suggestion apply action.type')
  const data = expectRecord(body.data ?? {}, 'copilot suggestion apply action.data')

  switch (type) {
    case 'create_entity':
    case 'create_relationship':
    case 'create_system':
      return { type, data } as CopilotSuggestionApplyAction
    case 'update_entity':
      return {
        type,
        entity_id: readOptionalNumber(body.entity_id, 'copilot suggestion apply action.entity_id') ?? invalidResponseShape('copilot suggestion apply action.entity_id'),
        data,
      } as CopilotSuggestionApplyAction
    case 'update_relationship':
      return {
        type,
        relationship_id: readOptionalNumber(body.relationship_id, 'copilot suggestion apply action.relationship_id') ?? invalidResponseShape('copilot suggestion apply action.relationship_id'),
        data,
      } as CopilotSuggestionApplyAction
    case 'update_system':
      return {
        type,
        system_id: readOptionalNumber(body.system_id, 'copilot suggestion apply action.system_id') ?? invalidResponseShape('copilot suggestion apply action.system_id'),
        data,
      } as CopilotSuggestionApplyAction
  }
}

function parseCopilotSuggestion(value: unknown): CopilotSuggestion {
  const body = expectRecord(value, 'copilot suggestion')
  return {
    suggestion_id: expectString(body.suggestion_id, 'copilot suggestion.suggestion_id'),
    kind: expectString(body.kind, 'copilot suggestion.kind'),
    title: expectString(body.title, 'copilot suggestion.title'),
    summary: expectString(body.summary, 'copilot suggestion.summary'),
    evidence_ids: expectStringArray(body.evidence_ids ?? [], 'copilot suggestion.evidence_ids'),
    target: parseCopilotSuggestionTarget(body.target),
    preview: parseCopilotSuggestionPreview(body.preview),
    apply: parseCopilotSuggestionApplyAction(body.apply),
    status: expectEnumValue(body.status, COPILOT_SUGGESTION_STATUSES, 'copilot suggestion.status'),
  }
}

function parseCopilotSessionResponse(value: unknown): CopilotSessionResponse {
  const body = expectRecord(value, 'copilot session response')
  return {
    session_id: expectString(body.session_id, 'copilot session response.session_id'),
    signature: expectString(body.signature, 'copilot session response.signature'),
    mode: expectEnumValue(body.mode, COPILOT_MODES, 'copilot session response.mode'),
    scope: expectEnumValue(body.scope, COPILOT_SCOPES, 'copilot session response.scope'),
    context: parseCopilotContextData(body.context),
    interaction_locale: expectString(body.interaction_locale, 'copilot session response.interaction_locale'),
    display_title: expectString(body.display_title, 'copilot session response.display_title'),
    created: expectBoolean(body.created, 'copilot session response.created'),
    created_at: expectString(body.created_at, 'copilot session response.created_at'),
  }
}

function parseCopilotRunResponse(value: unknown): CopilotRunResponse {
  const body = expectRecord(value, 'copilot run response')
  return {
    run_id: expectString(body.run_id, 'copilot run response.run_id'),
    status: expectEnumValue(body.status, COPILOT_RUN_STATUSES, 'copilot run response.status') as CopilotRunStatus,
    prompt: expectString(body.prompt, 'copilot run response.prompt'),
    answer: readOptionalString(body.answer) ?? null,
    trace: expectArray(body.trace ?? [], 'copilot run response.trace').map(parseCopilotTraceStep),
    evidence: expectArray(body.evidence ?? [], 'copilot run response.evidence').map(parseCopilotEvidence),
    suggestions: expectArray(body.suggestions ?? [], 'copilot run response.suggestions').map(parseCopilotSuggestion),
    error: readOptionalString(body.error) ?? null,
  }
}

function parseCopilotApplyResponse(value: unknown): CopilotApplyResponse {
  const body = expectRecord(value, 'copilot apply response')
  return {
    results: expectArray(body.results, 'copilot apply response.results').map((item) => {
      const result = expectRecord(item, 'copilot apply response.result')
      return {
        suggestion_id: expectString(result.suggestion_id, 'copilot apply response.result.suggestion_id'),
        success: expectBoolean(result.success, 'copilot apply response.result.success'),
        error_code: readOptionalString(result.error_code) ?? null,
        error_message: readOptionalString(result.error_message) ?? null,
      }
    }),
  }
}

function parseCopilotRunListResponse(value: unknown): CopilotRunResponse[] {
  return expectArray(value, 'copilot run list response').map(parseCopilotRunResponse)
}

export interface CopilotSessionOpenRequest {
  mode: CopilotMode
  scope: CopilotScope
  context?: {
    entity_id?: number
    tab?: CopilotContextTab
    surface?: CopilotContextSurface
    stage?: CopilotContextStage
  } | null
  interaction_locale?: string
  display_title?: string
}

export interface CopilotSessionResponse {
  session_id: string
  signature: string
  mode: CopilotMode
  scope: CopilotScope
  context: CopilotContextData | null
  interaction_locale: string
  display_title: string
  created: boolean
  created_at: string
}

export interface CopilotRunCreateRequest {
  prompt: string
  quick_action_id?: string | null
  resume_run_id?: string | null
}

export type CopilotRunResponse = CopilotRun

export interface CopilotApplyResponse {
  results: { suggestion_id: string; success: boolean; error_code?: string | null; error_message?: string | null }[]
}

export const copilotApi = {
  openSession: (novelId: number, data: CopilotSessionOpenRequest) =>
    requestParsed(`/api/novels/${novelId}/world/copilot/sessions`, parseCopilotSessionResponse, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  createRun: (novelId: number, sessionId: string, data: CopilotRunCreateRequest) =>
    requestParsed(`/api/novels/${novelId}/world/copilot/sessions/${sessionId}/runs`, parseCopilotRunResponse, {
      method: 'POST',
      headers: llmHeaders(),
      body: JSON.stringify(data),
    }),

  pollRun: (novelId: number, sessionId: string, runId: string, signal?: AbortSignal) =>
    requestParsed(`/api/novels/${novelId}/world/copilot/sessions/${sessionId}/runs/${runId}`, parseCopilotRunResponse, { signal }),

  listRuns: (novelId: number, sessionId: string, signal?: AbortSignal) =>
    requestParsed(`/api/novels/${novelId}/world/copilot/sessions/${sessionId}/runs`, parseCopilotRunListResponse, { signal }),

  applySuggestions: (novelId: number, sessionId: string, runId: string, suggestionIds: string[]) =>
    requestParsed(`/api/novels/${novelId}/world/copilot/sessions/${sessionId}/runs/${runId}/apply`, parseCopilotApplyResponse, {
      method: 'POST',
      body: JSON.stringify({ suggestion_ids: suggestionIds }),
    }),

  dismissSuggestions: (novelId: number, sessionId: string, runId: string, suggestionIds: string[]) =>
    request<{ ok: boolean }>(`/api/novels/${novelId}/world/copilot/sessions/${sessionId}/runs/${runId}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({ suggestion_ids: suggestionIds }),
    }),
}
