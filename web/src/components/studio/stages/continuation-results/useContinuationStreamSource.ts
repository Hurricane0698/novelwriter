import { useEffect, useRef, useState } from 'react'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import type { UiLocale } from '@/lib/uiMessages'
import { ApiError, streamContinuation } from '@/services/api'
import type { ContinueDebugSummary, ContinueResponse, Continuation } from '@/types/api'
import {
  buildContinuationMappingFromContinuations,
  resolveRequestFailureMessage,
  type ContinuationResultsLocationState,
  type ContinuationResultsT,
  type ContinuationStreamContext,
  type PersistResultsToUrl,
  type VariantState,
} from './helpers'
import {
  applyStreamEvent,
  resetStreamRuntime,
  resolveInitialStreamContext,
  resolveStreamTransportFailure,
} from './streamRuntime'

interface UseContinuationStreamSourceArgs {
  locationState: ContinuationResultsLocationState | null
  persisted: string | null
  locale: UiLocale
  t: ContinuationResultsT
  persistResultsToUrl: PersistResultsToUrl
}

interface UseContinuationStreamSourceResult {
  streamSourceId: string | null
  variants: VariantState[]
  fallbackNotice: string | null
  fallbackVersions: Continuation[]
  streamDebug: ContinueDebugSummary | null
  streamError: string | null
  isDone: boolean
  isQuotaExhausted: boolean
  isStreamMode: boolean
  isFallbackMode: boolean
  retryStream: () => void
}

export function useContinuationStreamSource({
  locationState,
  persisted,
  locale,
  t,
  persistResultsToUrl,
}: UseContinuationStreamSourceArgs): UseContinuationStreamSourceResult {
  const [fallbackResponse, setFallbackResponse] = useState<ContinueResponse | null>(null)
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null)
  const [variants, setVariants] = useState<VariantState[]>([])
  const [isDone, setIsDone] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isQuotaExhausted, setIsQuotaExhausted] = useState(false)
  const [streamDebug, setStreamDebug] = useState<ContinueDebugSummary | null>(null)
  const [streamAttempt, setStreamAttempt] = useState(0)

  const initialStreamRef = useRef<ContinuationStreamContext | null | undefined>(undefined)
  if (initialStreamRef.current === undefined) {
    initialStreamRef.current = resolveInitialStreamContext(persisted, locationState)
  }
  const streamCtx = initialStreamRef.current

  const abortRef = useRef(false)
  const abortCtrlRef = useRef<AbortController | null>(null)
  const continuationMapRef = useRef<Map<number, number>>(new Map())
  const totalVariantsRef = useRef<number>(0)
  const receivedStreamOutputRef = useRef(false)

  useEffect(() => {
    if (!streamCtx) return

    abortRef.current = false
    abortCtrlRef.current?.abort()
    const ctrl = new AbortController()
    abortCtrlRef.current = ctrl

    resetStreamRuntime(
      {
        continuationMapRef,
        totalVariantsRef,
        receivedStreamOutputRef,
      },
      {
        setFallbackNotice,
        setFallbackResponse,
        setIsDone,
        setIsQuotaExhausted,
        setStreamDebug,
        setStreamError,
        setVariants,
      },
    )

    const consume = async () => {
      try {
        for await (const event of streamContinuation(streamCtx.novelId, streamCtx.params, {
          signal: ctrl.signal,
          continuationRequestId: streamCtx.continuationRequestId,
        })) {
          if (abortRef.current || ctrl.signal.aborted) break

          applyStreamEvent(event, {
            refs: {
              continuationMapRef,
              totalVariantsRef,
              receivedStreamOutputRef,
            },
            setters: {
              setIsDone,
              setStreamDebug,
              setStreamError,
              setVariants,
            },
            persistResultsToUrl,
          })
        }
      } catch (error) {
        if (abortRef.current || ctrl.signal.aborted) return
        const transportFailure = await resolveStreamTransportFailure(error, {
          abortRef,
          signal: ctrl.signal,
          refs: {
            receivedStreamOutputRef,
          },
          setters: {
            setFallbackNotice,
            setFallbackResponse,
            setIsDone,
            setStreamDebug,
            setStreamError,
          },
          streamCtx,
          t,
        })
        if (transportFailure.handled) return

        const failure = resolveRequestFailureMessage(transportFailure.error, {
          locale,
          t,
          getLlmApiErrorMessage: (error, activeLocale) => (
            error instanceof ApiError ? getLlmApiErrorMessage(error, activeLocale) : null
          ),
        })
        setIsQuotaExhausted(failure.isQuotaExhausted)
        setStreamError(failure.message)
      }
    }

    void consume()
    return () => {
      abortRef.current = true
      ctrl.abort()
    }
  }, [locale, persistResultsToUrl, streamAttempt, streamCtx, t])

  useEffect(() => {
    if (!fallbackResponse) return
    persistResultsToUrl(
      buildContinuationMappingFromContinuations(fallbackResponse.continuations),
      fallbackResponse.continuations.length,
      fallbackResponse.debug ?? null,
    )
  }, [fallbackResponse, persistResultsToUrl])

  return {
    streamSourceId: streamCtx?.continuationRequestId ?? null,
    variants,
    fallbackNotice,
    fallbackVersions: fallbackResponse?.continuations ?? [],
    streamDebug,
    streamError,
    isDone,
    isQuotaExhausted,
    isStreamMode: streamCtx != null,
    isFallbackMode: (fallbackResponse?.continuations.length ?? 0) > 0,
    retryStream: () => setStreamAttempt((value) => value + 1),
  }
}
