import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import { api, ApiError, buildContinuationRequestId } from '@/services/api'
import type { ContinueDebugSummary, ContinueResponse, StreamEvent } from '@/types/api'
import {
  buildContinuationMapping,
  type ContinuationResultsLocationState,
  type ContinuationResultsT,
  type ContinuationStreamContext,
  type PersistResultsToUrl,
  type VariantState,
} from './helpers'

interface StreamRuntimeRefs {
  continuationMapRef: MutableRefObject<Map<number, number>>
  totalVariantsRef: MutableRefObject<number>
  receivedStreamOutputRef: MutableRefObject<boolean>
}

interface StreamRuntimeSetters {
  setFallbackNotice: Dispatch<SetStateAction<string | null>>
  setFallbackResponse: Dispatch<SetStateAction<ContinueResponse | null>>
  setIsDone: Dispatch<SetStateAction<boolean>>
  setStreamDebug: Dispatch<SetStateAction<ContinueDebugSummary | null>>
  setStreamError: Dispatch<SetStateAction<string | null>>
  setVariants: Dispatch<SetStateAction<VariantState[]>>
}

export function isEarlyStreamTransportFailure(error: unknown): boolean {
  if (error instanceof ApiError) return false
  if (!(error instanceof Error)) return false
  if (error instanceof TypeError) return true
  const message = error.message.toLowerCase()
  return (
    message.includes('malformed ndjson') ||
    message.includes('failed to fetch') ||
    message.includes('networkerror') ||
    message.includes('load failed')
  )
}

export function resolveInitialStreamContext(
  persisted: string | null,
  locationState: ContinuationResultsLocationState | null,
): ContinuationStreamContext | null {
  if (persisted || !locationState?.streamParams || !locationState?.novelId) return null
  return {
    novelId: locationState.novelId,
    params: locationState.streamParams,
    continuationRequestId: buildContinuationRequestId(),
  }
}

export function resetStreamRuntime(
  refs: StreamRuntimeRefs,
  setters: StreamRuntimeSetters,
): void {
  refs.continuationMapRef.current = new Map()
  refs.totalVariantsRef.current = 0
  refs.receivedStreamOutputRef.current = false
  setters.setVariants([])
  setters.setIsDone(false)
  setters.setStreamError(null)
  setters.setStreamDebug(null)
  setters.setFallbackResponse(null)
  setters.setFallbackNotice(null)
}

export function applyStreamEvent(
  event: StreamEvent,
  args: {
    refs: StreamRuntimeRefs
    setters: Pick<StreamRuntimeSetters, 'setIsDone' | 'setStreamDebug' | 'setStreamError' | 'setVariants'>
    persistResultsToUrl: PersistResultsToUrl
  },
): void {
  const { refs, setters, persistResultsToUrl } = args
  switch (event.type) {
    case 'start':
      refs.totalVariantsRef.current = event.total_variants
      if ('debug' in event) setters.setStreamDebug(event.debug ?? null)
      setters.setVariants(
        Array.from({ length: event.total_variants }, () => ({
          content: '',
          continuationId: null,
          isStreaming: true,
          error: null,
        })),
      )
      return
    case 'token':
      refs.receivedStreamOutputRef.current = true
      setters.setVariants((prev) => prev.map((variant, index) => (
        index === event.variant
          ? { ...variant, content: variant.content + event.content }
          : variant
      )))
      return
    case 'variant_done':
      refs.receivedStreamOutputRef.current = true
      refs.continuationMapRef.current.set(event.variant, event.continuation_id)
      setters.setVariants((prev) => prev.map((variant, index) => (
        index === event.variant
          ? {
              ...variant,
              content: event.content ?? variant.content,
              continuationId: event.continuation_id,
              isStreaming: false,
              error: null,
            }
          : variant
      )))
      return
    case 'done': {
      setters.setIsDone(true)
      const doneDebug = event.debug ?? null
      if (doneDebug) setters.setStreamDebug(doneDebug)
      persistResultsToUrl(
        buildContinuationMapping(refs.continuationMapRef.current.entries()),
        refs.totalVariantsRef.current,
        doneDebug,
      )
      return
    }
    case 'error':
      if (event.variant != null) {
        setters.setVariants((prev) => prev.map((variant, index) => (
          index === event.variant
            ? { ...variant, error: event.message, isStreaming: false }
            : variant
        )))
      } else {
        setters.setStreamError(event.message)
      }
  }
}

export async function resolveStreamTransportFailure(
  originalError: unknown,
  args: {
    abortRef: MutableRefObject<boolean>
    signal: AbortSignal
    refs: Pick<StreamRuntimeRefs, 'receivedStreamOutputRef'>
    setters: Pick<StreamRuntimeSetters, 'setFallbackNotice' | 'setFallbackResponse' | 'setIsDone' | 'setStreamDebug' | 'setStreamError'>
    streamCtx: ContinuationStreamContext | null
    t: ContinuationResultsT
  },
): Promise<{ handled: boolean; error: unknown }> {
  const { abortRef, signal, refs, setters, streamCtx, t } = args
  let resolvedError = originalError
  if (streamCtx && !refs.receivedStreamOutputRef.current && isEarlyStreamTransportFailure(resolvedError)) {
    try {
      const response = await api.continueNovel(
        streamCtx.novelId,
        streamCtx.params,
        {
          continuationRequestId: streamCtx.continuationRequestId,
        },
      )
      if (abortRef.current || signal.aborted) {
        return { handled: true, error: resolvedError }
      }
      setters.setFallbackResponse(response)
      setters.setFallbackNotice(t('continuation.results.streamFallbackNotice'))
      setters.setStreamDebug(response.debug ?? null)
      setters.setStreamError(null)
      setters.setIsDone(true)
      return { handled: true, error: resolvedError }
    } catch (fallbackError) {
      resolvedError = fallbackError
    }
  }
  return { handled: false, error: resolvedError }
}
