import {
  DEFAULT_UI_LOCALE,
  normalizeUiLocale,
  readDocumentUiLocale,
} from '@/lib/uiLocale'

export type CopilotMode = 'research' | 'current_entity' | 'draft_cleanup'
export type CopilotScope = 'whole_book' | 'current_entity' | 'current_tab'
export type CopilotContextTab = 'entities' | 'relationships' | 'review' | 'systems'
export type CopilotContextSurface = 'studio' | 'atlas'
export type CopilotContextStage =
  | 'chapter'
  | 'write'
  | 'results'
  | 'entity'
  | 'relationship'
  | 'system'
  | 'review'
export type CopilotTargetTab = 'entities' | 'relationships' | 'systems' | 'review'
export type CopilotReviewKind = 'entities' | 'relationships' | 'systems'
const DEFAULT_COPILOT_INTERACTION_LOCALE = DEFAULT_UI_LOCALE

interface CopilotUiContextData {
  surface?: CopilotContextSurface
  stage?: CopilotContextStage
}

export type CopilotWholeBookContext = CopilotUiContextData & {
  tab?: CopilotContextTab
}

export type CopilotCurrentEntityContext = CopilotUiContextData & {
  entity_id: number
  tab?: 'entities'
}

export type CopilotRelationshipResearchContext = CopilotUiContextData & {
  tab: 'relationships'
  entity_id?: number
}

export type CopilotDraftCleanupContext = CopilotUiContextData & {
  tab: 'review'
}

export type CopilotContextData =
  | CopilotWholeBookContext
  | CopilotCurrentEntityContext
  | CopilotRelationshipResearchContext
  | CopilotDraftCleanupContext

export type CopilotWholeBookPrefill = {
  mode: 'research'
  scope: 'whole_book'
  context?: CopilotWholeBookContext
}

export type CopilotCurrentEntityPrefill = {
  mode: 'current_entity'
  scope: 'current_entity'
  context: CopilotCurrentEntityContext
}

export type CopilotCurrentTabResearchPrefill = {
  mode: 'research'
  scope: 'current_tab'
  context: CopilotRelationshipResearchContext
}

export type CopilotDraftCleanupPrefill = {
  mode: 'draft_cleanup'
  scope: 'current_tab'
  context: CopilotDraftCleanupContext
}

export type CopilotPrefill =
  | CopilotWholeBookPrefill
  | CopilotCurrentEntityPrefill
  | CopilotCurrentTabResearchPrefill
  | CopilotDraftCleanupPrefill

interface CopilotSessionIdentityContext {
  entity_id?: number
  tab?: CopilotContextTab
}

export interface NovelCopilotSession {
  sessionId: string
  signature: string
  prefill: CopilotPrefill
  displayTitle: string
  novelId: number
  interactionLocale: string
  backendSessionId: string | null
}

export interface OpenNovelCopilotOptions {
  displayTitle?: string
}

export type CopilotRunStatus = 'idle' | 'queued' | 'running' | 'completed' | 'error' | 'interrupted'

export interface CopilotEvidence {
  evidence_id: string
  source_type: string
  source_ref?: Record<string, unknown> | null
  title: string
  excerpt: string
  why_relevant: string
  pack_id?: string | null
  source_refs?: Array<Record<string, unknown>>
  anchor_terms?: string[]
  support_count?: number | null
  preview_excerpt?: string | null
  expanded?: boolean
}

export interface CopilotSuggestionTarget {
  resource: 'entity' | 'relationship' | 'system'
  resource_id: number | null
  label: string
  tab: CopilotTargetTab
  entity_id?: number | null
  review_kind?: CopilotReviewKind
  highlight_id?: number | null
}

export interface CopilotFieldDelta {
  field: string
  label: string
  before: string | null
  after: string
}

export interface CopilotSuggestionPreview {
  target_label: string
  summary: string
  field_deltas: CopilotFieldDelta[]
  evidence_quotes: string[]
  actionable: boolean
  non_actionable_reason?: string | null
}

export type CopilotSuggestionApplyAction =
  | {
      type: 'create_entity'
      data: Record<string, unknown>
    }
  | {
      type: 'update_entity'
      entity_id: number
      data: Record<string, unknown>
    }
  | {
      type: 'create_relationship'
      data: Record<string, unknown>
    }
  | {
      type: 'update_relationship'
      relationship_id: number
      data: Record<string, unknown>
    }
  | {
      type: 'create_system'
      data: Record<string, unknown>
    }
  | {
      type: 'update_system'
      system_id: number
      data: Record<string, unknown>
    }

export interface CopilotSuggestion {
  suggestion_id: string
  kind: string
  title: string
  summary: string
  evidence_ids: string[]
  target: CopilotSuggestionTarget
  preview: CopilotSuggestionPreview
  apply: CopilotSuggestionApplyAction | null
  status: 'pending' | 'applied' | 'dismissed'
}

export interface CopilotTraceStep {
  step_id: string
  kind: string
  status: string
  summary: string
}

export interface CopilotRun {
  run_id: string
  status: CopilotRunStatus
  prompt: string
  answer?: string | null
  trace: CopilotTraceStep[]
  evidence: CopilotEvidence[]
  suggestions: CopilotSuggestion[]
  error?: string | null
}

export function normalizeCopilotInteractionLocale(raw: string | null | undefined) {
  return normalizeUiLocale(raw, DEFAULT_COPILOT_INTERACTION_LOCALE)
}

export function getDefaultCopilotInteractionLocale() {
  return readDocumentUiLocale() ?? DEFAULT_COPILOT_INTERACTION_LOCALE
}

export function buildCopilotSessionSignature(
  prefill: CopilotPrefill,
  novelId: number,
  interactionLocale: string,
) {
  const context = normalizeCopilotSessionContext(prefill)
  return JSON.stringify({
    novel_id: novelId,
    interaction_locale: normalizeCopilotInteractionLocale(interactionLocale),
    mode: prefill.mode,
    scope: prefill.scope,
    entity_id: context?.entity_id ?? null,
    tab: context?.tab ?? null,
  })
}

function normalizeCopilotSessionContext(
  prefill: CopilotPrefill,
): CopilotSessionIdentityContext | null {
  if (prefill.scope === 'whole_book') return null

  if (prefill.scope === 'current_entity') {
    return { entity_id: prefill.context.entity_id }
  }

  const normalized: CopilotSessionIdentityContext = {
    tab: prefill.context.tab,
  }

  if ('entity_id' in prefill.context && typeof prefill.context.entity_id === 'number') {
    normalized.entity_id = prefill.context.entity_id
  }

  return normalized
}
