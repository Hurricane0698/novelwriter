import type { ContinueDebugSummary, PostcheckWarning, ProseWarning } from '@/types/api'
import { normalizePostcheckWarning, normalizeProseWarning } from '@/lib/postcheckWarnings'

const DEBUG_STORAGE_PREFIX = 'novwr_gen_debug_'
const WARNING_STORAGE_PREFIX = 'novwr_gen_warnings_'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function normalizeStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function normalizeNumberList(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
    : []
}

function normalizePostcheckWarnings(value: unknown): PostcheckWarning[] {
  if (!Array.isArray(value)) return []
  return value
    .map(normalizePostcheckWarning)
    .filter((warning): warning is PostcheckWarning => warning != null)
}

function normalizeProseWarnings(value: unknown): ProseWarning[] {
  if (!Array.isArray(value)) return []
  return value
    .map(normalizeProseWarning)
    .filter((warning): warning is ProseWarning => warning != null)
}

function normalizeContinueDebugSummary(value: unknown): ContinueDebugSummary | null {
  if (!isRecord(value)) return null

  const contextChapters = typeof value.context_chapters === 'number' && Number.isFinite(value.context_chapters)
    ? value.context_chapters
    : 0
  const driftWarnings = normalizePostcheckWarnings(value.drift_warnings)
  const legacyDriftWarnings = driftWarnings.length === 0
    ? normalizePostcheckWarnings(value.postcheck_warnings)
    : []

  return {
    context_chapters: contextChapters,
    injected_systems: normalizeStringList(value.injected_systems),
    injected_entities: normalizeStringList(value.injected_entities),
    injected_relationships: normalizeStringList(value.injected_relationships),
    injected_context_summaries: normalizeStringList(value.injected_context_summaries),
    relevant_entity_ids: normalizeNumberList(value.relevant_entity_ids),
    ambiguous_keywords_disabled: normalizeStringList(value.ambiguous_keywords_disabled),
    drift_warnings: driftWarnings.length > 0 ? driftWarnings : legacyDriftWarnings,
    prose_warnings: normalizeProseWarnings(value.prose_warnings),
  }
}

export function saveGenerationResultsDebug(continuations: string, debug: ContinueDebugSummary) {
  try {
    sessionStorage.setItem(`${DEBUG_STORAGE_PREFIX}${continuations}`, JSON.stringify(debug))
  } catch {
    // Ignore storage failures; results reload can still fall back to the URL ids.
  }
}

export function readGenerationResultsDebug(continuations: string): ContinueDebugSummary | null {
  try {
    const raw = sessionStorage.getItem(`${DEBUG_STORAGE_PREFIX}${continuations}`)
    if (!raw) return null
    return normalizeContinueDebugSummary(JSON.parse(raw))
  } catch {
    return null
  }
}

export function readGenerationResultsWarnings(continuations: string): PostcheckWarning[] {
  const debug = readGenerationResultsDebug(continuations)
  if (debug) return debug.drift_warnings

  try {
    const raw = sessionStorage.getItem(`${WARNING_STORAGE_PREFIX}${continuations}`)
    if (!raw) return []
    return normalizePostcheckWarnings(JSON.parse(raw))
  } catch {
    return []
  }
}
