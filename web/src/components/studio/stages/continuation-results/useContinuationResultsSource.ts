import type { Location, NavigateFunction } from 'react-router-dom'
import type { UiLocale } from '@/lib/uiMessages'
import type { ContinueDebugSummary, ContinueResponse, Continuation, PostcheckWarning } from '@/types/api'
import {
  buildContinuationMappingFromContinuations,
  type ContinuationResultsLocationState,
  type ContinuationResultsT,
  type VariantState,
} from './helpers'
import { useContinuationResultsUrlPersistence } from './useContinuationResultsUrlPersistence'
import { useContinuationStreamSource } from './useContinuationStreamSource'
import { usePersistedContinuationReplay } from './usePersistedContinuationReplay'

interface UseContinuationResultsSourceArgs {
  novelId: number
  activeChapterNum: number | null
  location: Location
  navigate: NavigateFunction
  locale: UiLocale
  t: ContinuationResultsT
}

interface UseContinuationResultsSourceResult {
  sourceIdentity: string
  locationState: ContinuationResultsLocationState | null
  legacyResponse: ContinueResponse | undefined
  persisted: string | null
  variants: VariantState[]
  fallbackNotice: string | null
  fallbackVersions: Continuation[]
  nonStreamVersions: Continuation[]
  persistedDebug: ContinueDebugSummary | null
  persistedError: string | null
  reloadedWarnings: PostcheckWarning[]
  streamDebug: ContinueDebugSummary | null
  streamError: string | null
  isDone: boolean
  isQuotaExhausted: boolean
  isStreamMode: boolean
  isFallbackMode: boolean
  isLegacyMode: boolean
  isReloadMode: boolean
  retryStream: () => void
  retryReload: () => void
}

export function useContinuationResultsSource({
  novelId,
  activeChapterNum,
  location,
  navigate,
  locale,
  t,
}: UseContinuationResultsSourceArgs): UseContinuationResultsSourceResult {
  const locationState = location.state as ContinuationResultsLocationState | null
  const legacyResponse = locationState?.response
  const legacyVersions: Continuation[] = legacyResponse?.continuations ?? []
  const persisted = new URLSearchParams(location.search).get('continuations')

  const persistResultsToUrl = useContinuationResultsUrlPersistence({
    activeChapterNum,
    location,
    navigate,
  })

  const {
    streamSourceId,
    variants,
    fallbackNotice,
    fallbackVersions,
    streamDebug,
    streamError,
    isDone,
    isQuotaExhausted,
    isStreamMode,
    isFallbackMode,
    retryStream,
  } = useContinuationStreamSource({
    locationState,
    persisted,
    locale,
    t,
    persistResultsToUrl,
  })

  const isReloadMode = !isStreamMode && legacyVersions.length === 0 && !!persisted

  const {
    persistedVersions,
    persistedDebug,
    persistedError,
    reloadedWarnings,
    retryReload,
  } = usePersistedContinuationReplay({
    isReloadMode,
    novelId,
    persisted,
  })

  const nonStreamVersions = persistedVersions ?? legacyVersions
  const isLegacyMode = !isStreamMode && nonStreamVersions.length > 0
  const sourceIdentity = streamSourceId !== null
    ? `stream:${streamSourceId}`
    : persisted
      ? `persisted:${persisted}`
      : legacyVersions.length > 0
        ? `legacy:${buildContinuationMappingFromContinuations(legacyVersions)}`
        : 'empty'

  return {
    sourceIdentity,
    locationState,
    legacyResponse,
    persisted,
    variants,
    fallbackNotice,
    fallbackVersions,
    nonStreamVersions,
    persistedDebug,
    persistedError,
    reloadedWarnings,
    streamDebug,
    streamError,
    isDone,
    isQuotaExhausted,
    isStreamMode,
    isFallbackMode,
    isLegacyMode,
    isReloadMode,
    retryStream,
    retryReload,
  }
}
