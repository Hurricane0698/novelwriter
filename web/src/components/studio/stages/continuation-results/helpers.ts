import type { UiLocale, UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import type {
  ContinueDebugSummary,
  ContinueRequest,
  ContinueResponse,
  Continuation,
  PostcheckWarning,
  ProseWarning,
} from '@/types/api'

export type ContinuationResultsT = (key: UiMessageKey, params?: UiMessageParams) => string

export interface ContinuationResultsLocationState {
  streamParams?: ContinueRequest
  novelId?: number
  response?: ContinueResponse
  studioResultsDebug?: ContinueDebugSummary | null
}

export interface ContinuationStreamContext {
  novelId: number
  params: NonNullable<ContinuationResultsLocationState['streamParams']>
  continuationRequestId: string
}

export interface VariantState {
  content: string
  continuationId: number | null
  isStreaming: boolean
  error: string | null
}

export type PersistResultsToUrl = (
  mapping: string,
  total: number,
  debugSummary: ContinueDebugSummary | null,
) => void

export interface ResolveResultsDebugArgs {
  isStreamMode: boolean
  streamDebug: ContinueDebugSummary | null
  legacyDebug?: ContinueDebugSummary | null
  persistedDebug?: ContinueDebugSummary | null
  studioResultsDebug?: ContinueDebugSummary | null
}

export interface ResolveDriftWarningsArgs {
  isStreamMode: boolean
  isDone: boolean
  streamDebug: ContinueDebugSummary | null
  legacyDebug?: ContinueDebugSummary | null
  reloadedWarnings: PostcheckWarning[]
}

export interface ResolveProseWarningsArgs {
  isStreamMode: boolean
  isFallbackMode: boolean
  isDone: boolean
  streamDebug: ContinueDebugSummary | null
  legacyDebug?: ContinueDebugSummary | null
  persistedDebug?: ContinueDebugSummary | null
  studioResultsDebug?: ContinueDebugSummary | null
}

export interface StatusError extends Error {
  status: number
}

export function buildContinuationMapping(entries: Iterable<[number, number]>): string {
  return Array.from(entries)
    .sort((a, b) => a[0] - b[0])
    .map(([variant, id]) => `${variant}:${id}`)
    .join(',')
}

export function buildContinuationMappingFromContinuations(continuations: Array<Pick<Continuation, 'id'>>): string {
  return continuations
    .map((continuation, index) => `${index}:${continuation.id}`)
    .join(',')
}

export function parsePersistedContinuationIds(mapping: string): number[] {
  return mapping
    .split(',')
    .map((pair) => pair.trim())
    .filter(Boolean)
    .map((pair) => {
      const [, idRaw] = pair.split(':')
      return Number.parseInt((idRaw ?? '').trim(), 10)
    })
    .filter((id) => Number.isFinite(id))
}

export function resolveResultsDebug({
  isStreamMode,
  streamDebug,
  legacyDebug,
  persistedDebug,
  studioResultsDebug,
}: ResolveResultsDebugArgs): ContinueDebugSummary | null {
  return isStreamMode
    ? streamDebug
    : (legacyDebug ?? persistedDebug ?? studioResultsDebug ?? null)
}

export function resolveDriftWarnings({
  isStreamMode,
  isDone,
  streamDebug,
  legacyDebug,
  reloadedWarnings,
}: ResolveDriftWarningsArgs): PostcheckWarning[] {
  if (isStreamMode) return isDone ? (streamDebug?.drift_warnings ?? []) : []
  if (legacyDebug?.drift_warnings?.length) return legacyDebug.drift_warnings
  return reloadedWarnings
}

export function resolveProseWarnings({
  isStreamMode,
  isFallbackMode,
  isDone,
  streamDebug,
  legacyDebug,
  persistedDebug,
  studioResultsDebug,
}: ResolveProseWarningsArgs): ProseWarning[] {
  if (isStreamMode) {
    return isFallbackMode
      ? (streamDebug?.prose_warnings ?? [])
      : (isDone ? (streamDebug?.prose_warnings ?? []) : [])
  }
  return legacyDebug?.prose_warnings ?? persistedDebug?.prose_warnings ?? studioResultsDebug?.prose_warnings ?? []
}

export function resolveRequestFailureMessage(
  resolvedError: unknown,
  args: {
    locale: UiLocale
    t: ContinuationResultsT
    getLlmApiErrorMessage: (error: StatusError, locale: UiLocale) => string | null
  },
): string {
  const { locale, t, getLlmApiErrorMessage } = args
  if (isStatusError(resolvedError)) {
    const llmMessage = getLlmApiErrorMessage(resolvedError, locale)
    if (llmMessage) {
      return llmMessage
    }
    if (resolvedError.status === 503) {
      return t('continuation.results.serviceBusy')
    }
    return t('continuation.results.requestFailed', { status: resolvedError.status })
  }
  return resolvedError instanceof Error ? resolvedError.message : 'Stream failed'
}

function isStatusError(resolvedError: unknown): resolvedError is StatusError {
  return resolvedError instanceof Error && typeof (resolvedError as { status?: unknown }).status === 'number'
}
