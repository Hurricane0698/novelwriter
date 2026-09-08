import type React from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  type CopilotContextData,
  type CopilotRun,
  type CopilotScope,
  type NovelCopilotSession,
} from '@/types/copilot'
import { ApiError, copilotApi } from '@/services/api'
import { QueryClient, useQueryClient } from '@tanstack/react-query'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useToast } from '@/components/world-model/shared/useToast'
import { worldKeys } from '@/hooks/world/keys'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'

// ---------------------------------------------------------------------------
// Run state container (shared across sessions)
// ---------------------------------------------------------------------------

interface NovelCopilotRunsState {
  runsBySessionId: Record<string, CopilotRun[]>
  setRunsBySessionId: React.Dispatch<React.SetStateAction<Record<string, CopilotRun[]>>>
  timeoutIdsRef: React.MutableRefObject<Record<string, ReturnType<typeof setTimeout>>>
}

export function useNovelCopilotRunsState(sessions: NovelCopilotSession[]): NovelCopilotRunsState {
  const [runsBySessionId, setRunsBySessionId] = useState<Record<string, CopilotRun[]>>({})
  const timeoutIdsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    const timeoutIds = timeoutIdsRef.current
    return () => {
      Object.values(timeoutIds).forEach((timeoutId) => clearTimeout(timeoutId))
    }
  }, [])

  useEffect(() => {
    const activeSessionIds = new Set(sessions.map((session) => session.sessionId))

    Object.entries(timeoutIdsRef.current).forEach(([sessionId, timeoutId]) => {
      if (activeSessionIds.has(sessionId)) return
      clearTimeout(timeoutId)
      delete timeoutIdsRef.current[sessionId]
    })

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRunsBySessionId((prev) => {
      const nextEntries = Object.entries(prev).filter(([sessionId]) => activeSessionIds.has(sessionId))
      if (nextEntries.length === Object.keys(prev).length) return prev
      return Object.fromEntries(nextEntries)
    })
  }, [sessions])

  return useMemo(() => ({
    runsBySessionId,
    setRunsBySessionId,
    timeoutIdsRef,
  }), [runsBySessionId])
}

// ---------------------------------------------------------------------------
// Main runs hook
// ---------------------------------------------------------------------------

interface UseNovelCopilotRunsParams {
  sessions: NovelCopilotSession[]
  focusedSessionId: string | null
  runsBySessionId: Record<string, CopilotRun[]>
  setRunsBySessionId: React.Dispatch<React.SetStateAction<Record<string, CopilotRun[]>>>
  timeoutIdsRef: React.MutableRefObject<Record<string, ReturnType<typeof setTimeout>>>
  resolveBackendSessionId: (sessionId: string) => Promise<string>
}

export interface NovelCopilotRunControllerState {
  focusedSession: NovelCopilotSession | null
  activeRun: CopilotRun | null
  getSessionRun: (sessionId: string) => CopilotRun | null
  getSessionRuns: (sessionId: string) => CopilotRun[]
  submitPrompt: (
    sessionId: string,
    prompt: string,
    scope: CopilotScope,
    context?: CopilotContextData,
    quickAction?: string,
  ) => Promise<boolean>
  retryInterruptedRun: (sessionId: string, runId: string) => Promise<boolean>
  applySuggestions: (sessionId: string, runId: string, suggestionIds: string[]) => Promise<boolean>
  dismissSuggestions: (sessionId: string, runId: string, suggestionIds: string[]) => Promise<void>
}

const POLL_INTERVAL_MS = 1500
const POLL_MAX_BACKOFF_MS = 12_000
const POLL_MAX_CONSECUTIVE_FAILURES = 5

function isTerminalPollError(error: unknown) {
  if (!(error instanceof ApiError)) return false
  if (error.status === 401 || error.status === 403) return true
  if (error.status === 404) return true
  if (error.status === 409) return true
  return false
}

function getNextPollDelayMs(consecutiveFailures: number) {
  const multiplier = Math.max(1, 2 ** consecutiveFailures)
  return Math.min(POLL_INTERVAL_MS * multiplier, POLL_MAX_BACKOFF_MS)
}

function getPollFailureMessage(error: unknown, message: (key: string) => string) {
  if (error instanceof ApiError && error.status === 404) {
    return message('copilot.errors.pollRunNotFound')
  }
  return message('copilot.errors.connectionInterrupted')
}

function readApiErrorDetailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (!detail || typeof detail !== 'object') return null
  const message = (detail as { message?: unknown }).message
  return typeof message === 'string' ? message : null
}

function isQuotaExhaustedApiError(error: ApiError) {
  if (error.code === 'generation_quota_exhausted' || error.code === 'generation_quota_insufficient') {
    return true
  }
  if (error.status !== 429) return false

  const detailMessage = `${readApiErrorDetailMessage(error.detail) ?? ''} ${typeof error.detail === 'string' ? error.detail : ''}`.toLowerCase()
  return detailMessage.includes('quota') || detailMessage.includes('额度')
}

function appendSessionRun(
  prev: Record<string, CopilotRun[]>,
  sessionId: string,
  run: CopilotRun,
) {
  return {
    ...prev,
    [sessionId]: [...(prev[sessionId] ?? []), run],
  }
}

function updateSessionRunById(
  prev: Record<string, CopilotRun[]>,
  sessionId: string,
  runId: string,
  updater: (run: CopilotRun) => CopilotRun,
) {
  const runs = prev[sessionId] ?? []
  const nextRuns = runs.map((run) => (run.run_id === runId ? updater(run) : run))
  if (nextRuns === runs) return prev
  return { ...prev, [sessionId]: nextRuns }
}

function replaceSessionRun(
  prev: Record<string, CopilotRun[]>,
  sessionId: string,
  targetRunId: string,
  nextRun: CopilotRun,
) {
  const runs = prev[sessionId] ?? []
  const index = runs.findIndex((run) => run.run_id === targetRunId)
  if (index === -1) {
    return appendSessionRun(prev, sessionId, nextRun)
  }
  const nextRuns = [...runs]
  nextRuns[index] = nextRun
  return { ...prev, [sessionId]: nextRuns }
}

export function collectInvalidateQueryKeysForAppliedSuggestions(
  novelId: number,
  suggestions: CopilotRun['suggestions'],
) {
  const keys = new Map<string, readonly unknown[]>()
  const add = (key: readonly unknown[]) => {
    keys.set(JSON.stringify(key), key)
  }

  suggestions.forEach((suggestion) => {
    switch (suggestion.apply?.type) {
      case 'create_entity':
        add(worldKeys.entities(novelId))
        break
      case 'update_entity':
        add(worldKeys.entities(novelId))
        add(worldKeys.entity(novelId, suggestion.apply.entity_id))
        break
      case 'create_relationship':
      case 'update_relationship':
        add(worldKeys.relationships(novelId))
        break
      case 'create_system':
        add(worldKeys.systems(novelId))
        break
      case 'update_system':
        add(worldKeys.systems(novelId))
        add(worldKeys.system(novelId, suggestion.apply.system_id))
        break
      default:
        add(worldKeys.all(novelId))
        break
    }
  })

  return [...keys.values()]
}

function invalidateWorldQueriesForAppliedSuggestions(
  queryClient: QueryClient,
  novelId: number,
  suggestions: CopilotRun['suggestions'],
) {
  const keys = collectInvalidateQueryKeysForAppliedSuggestions(novelId, suggestions)
  if (keys.length === 0) return
  keys.forEach((key) => {
    void queryClient.invalidateQueries({ queryKey: key })
  })
}

export function useNovelCopilotRuns({
  sessions,
  focusedSessionId,
  runsBySessionId,
  setRunsBySessionId,
  timeoutIdsRef,
  resolveBackendSessionId,
}: UseNovelCopilotRunsParams): NovelCopilotRunControllerState {
  const { t } = useUiLocale()
  const sessionsById = useMemo(
    () => new Map(sessions.map((session) => [session.sessionId, session])),
    [sessions],
  )
  const sessionsByIdRef = useRef(sessionsById)
  const hydratingSessionIdsRef = useRef<Set<string>>(new Set())
  const pollFailureCountsRef = useRef<Record<string, number>>({})
  const queryClient = useQueryClient()
  const { toast } = useToast()

  useEffect(() => {
    sessionsByIdRef.current = sessionsById
  }, [sessionsById])

  useEffect(() => {
    const activeSessionIds = new Set(sessions.map((session) => session.sessionId))
    Object.keys(pollFailureCountsRef.current).forEach((sessionId) => {
      if (activeSessionIds.has(sessionId)) return
      delete pollFailureCountsRef.current[sessionId]
    })
  }, [sessions])

  const focusedSession = focusedSessionId ? sessionsById.get(focusedSessionId) ?? null : null
  const activeRuns = focusedSessionId ? runsBySessionId[focusedSessionId] ?? [] : []
  const activeRun = activeRuns[activeRuns.length - 1] ?? null

  const getSessionRun = useCallback(
    (sessionId: string) => {
      const runs = runsBySessionId[sessionId] ?? []
      return runs[runs.length - 1] ?? null
    },
    [runsBySessionId],
  )

  const getSessionRuns = useCallback(
    (sessionId: string) => runsBySessionId[sessionId] ?? [],
    [runsBySessionId],
  )

  const getApplyFailureMessage = useCallback((result: { error_code?: string | null; error_message?: string | null }) => {
    if (result.error_message && result.error_message.trim()) return result.error_message
    switch (result.error_code) {
      case 'copilot_target_stale':
        return t('copilot.errors.applyTargetStale')
      case 'not_actionable':
        return t('copilot.errors.applyNotActionable')
      case 'suggestion_not_found':
        return t('copilot.errors.applySuggestionNotFound')
      default:
        return t('copilot.errors.applyFailed')
    }
  }, [t])

  const getRunCreateFailureMessage = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      switch (error.code) {
        case 'session_run_active':
          return t('copilot.errors.sessionRunActive')
        case 'too_many_active_runs':
          return t('copilot.errors.tooManyActiveRuns')
        case 'too_many_global_runs':
          return t('copilot.errors.tooManyGlobalRuns')
        case 'resume_run_not_found':
          return t('copilot.errors.resumeRunNotFound')
        case 'resume_run_not_interrupted':
          return t('copilot.errors.resumeRunNotInterrupted')
        case 'resume_prompt_mismatch':
          return t('copilot.errors.resumePromptMismatch')
        case 'resume_run_not_resumable':
          return t('copilot.errors.resumeRunNotResumable')
        default: {
          if (isQuotaExhaustedApiError(error)) {
            return t('copilot.errors.quotaExhausted')
          }
          const llmMessage = getLlmApiErrorMessage(error)
          if (llmMessage) return llmMessage
          if (error.status === 429) return t('copilot.errors.requestBusy')
          if (error.status === 503) return t('copilot.errors.serviceUnavailable')
          if (error.status === 409) return t('copilot.errors.sessionConflict')
        }
      }
    }
    return t('copilot.errors.runCreateFailed')
  }, [t])

  // -----------------------------------------------------------------------
  // Polling
  // -----------------------------------------------------------------------

  const startPolling = useCallback((
    localSessionId: string,
    sessionNovelId: number,
    backendSessionId: string,
    runId: string,
  ) => {
    const prev = timeoutIdsRef.current[localSessionId]
    if (prev) clearTimeout(prev)
    pollFailureCountsRef.current[localSessionId] = 0

    const clearPolling = () => {
      const timeoutId = timeoutIdsRef.current[localSessionId]
      if (timeoutId) clearTimeout(timeoutId)
      delete timeoutIdsRef.current[localSessionId]
      delete pollFailureCountsRef.current[localSessionId]
    }

    const schedulePoll = (delayMs: number) => {
      timeoutIdsRef.current[localSessionId] = setTimeout(async () => {
        try {
          const session = sessionsByIdRef.current.get(localSessionId)
          if (!session || session.backendSessionId !== backendSessionId) {
            clearPolling()
            return
          }

          const resp = await copilotApi.pollRun(sessionNovelId, backendSessionId, runId)
          pollFailureCountsRef.current[localSessionId] = 0

          setRunsBySessionId((prev) => {
            if (!sessionsByIdRef.current.has(localSessionId)) return prev
            const sessionRuns = prev[localSessionId] ?? []
            if (!sessionRuns.some((run) => run.run_id === runId)) return prev
            return updateSessionRunById(prev, localSessionId, runId, () => resp)
          })

          if (resp.status === 'queued' || resp.status === 'running') {
            schedulePoll(POLL_INTERVAL_MS)
          } else {
            clearPolling()
          }
        } catch (error) {
          const session = sessionsByIdRef.current.get(localSessionId)
          if (!session || session.backendSessionId !== backendSessionId) {
            clearPolling()
            return
          }

          const nextFailureCount = (pollFailureCountsRef.current[localSessionId] ?? 0) + 1
          pollFailureCountsRef.current[localSessionId] = nextFailureCount

          if (
            !isTerminalPollError(error)
            && nextFailureCount < POLL_MAX_CONSECUTIVE_FAILURES
          ) {
            schedulePoll(getNextPollDelayMs(nextFailureCount))
            return
          }

          const errorMessage = getPollFailureMessage(error, (key) => t(key as never))
          setRunsBySessionId((prev) => {
            if (!sessionsByIdRef.current.has(localSessionId)) return prev
            const sessionRuns = prev[localSessionId] ?? []
            const currentRun = sessionRuns.find((run) => run.run_id === runId)
            if (!currentRun) return prev
            return updateSessionRunById(prev, localSessionId, runId, (run) => ({
              ...run,
              status: 'error',
              error: errorMessage,
            }))
          })
          clearPolling()
        }
      }, delayMs)
    }

    schedulePoll(POLL_INTERVAL_MS)
  }, [setRunsBySessionId, t, timeoutIdsRef])

  useEffect(() => {
    const session = focusedSession
    if (!session || activeRuns.length > 0 || !session.backendSessionId) return
    if (hydratingSessionIdsRef.current.has(session.sessionId)) return
    const hydratedBackendSessionId = session.backendSessionId

    let cancelled = false
    hydratingSessionIdsRef.current.add(session.sessionId)

    void copilotApi.listRuns(session.novelId, hydratedBackendSessionId)
      .then((resp) => {
        if (cancelled) return

        const currentSession = sessionsByIdRef.current.get(session.sessionId)
        if (!currentSession) return
        if (currentSession.backendSessionId !== hydratedBackendSessionId) return

        setRunsBySessionId((prev) => {
          if (!sessionsByIdRef.current.has(session.sessionId)) return prev
          if ((prev[session.sessionId] ?? []).length > 0) return prev
          return {
            ...prev,
            [session.sessionId]: resp,
          }
        })

        const latestRun = resp[resp.length - 1]
        if (latestRun && (latestRun.status === 'queued' || latestRun.status === 'running')) {
          startPolling(session.sessionId, session.novelId, hydratedBackendSessionId, latestRun.run_id)
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404 && error.code === 'run_not_found') {
          return
        }
      })
      .finally(() => {
        hydratingSessionIdsRef.current.delete(session.sessionId)
      })

    return () => {
      cancelled = true
    }
  }, [activeRuns.length, focusedSession, setRunsBySessionId, startPolling])

  // -----------------------------------------------------------------------
  // Submit prompt
  // -----------------------------------------------------------------------

  const submitPrompt = useCallback(
    async (sessionId: string, prompt: string, _scope: CopilotScope, _context?: CopilotContextData, quickAction?: string) => {
      const session = sessionsByIdRef.current.get(sessionId)
      if (!session) return false

      const sessionRuns = runsBySessionId[sessionId] ?? []
      const existingRun = sessionRuns[sessionRuns.length - 1] ?? null
      if (existingRun && (existingRun.status === 'queued' || existingRun.status === 'running')) {
        return false
      }

      const optimisticRunId = `pending_${Date.now()}`

      setRunsBySessionId((prev) =>
        appendSessionRun(prev, sessionId, {
          run_id: optimisticRunId,
          status: 'queued',
          prompt,
          trace: [{ step_id: 's0', kind: 'init', status: 'running', summary: t('copilot.errors.connecting') }],
          evidence: [],
          suggestions: [],
        }),
      )

      try {
        const backendSessionId = await resolveBackendSessionId(sessionId)
        if (!sessionsByIdRef.current.has(sessionId)) return false

        const resp = await copilotApi.createRun(session.novelId, backendSessionId, {
          prompt,
          quick_action_id: quickAction ?? undefined,
        })
        if (!sessionsByIdRef.current.has(sessionId)) return false

        setRunsBySessionId((prev) => replaceSessionRun(prev, sessionId, optimisticRunId, resp))

        if (resp.status === 'queued' || resp.status === 'running') {
          startPolling(sessionId, session.novelId, backendSessionId, resp.run_id)
        }

        return true
      } catch (err) {
        const message = getRunCreateFailureMessage(err)
        setRunsBySessionId((prev) => {
          if (!sessionsByIdRef.current.has(sessionId)) return prev
          return replaceSessionRun(prev, sessionId, optimisticRunId, {
              run_id: `error_${Date.now()}`,
              status: 'error',
              prompt,
              trace: [],
              evidence: [],
              suggestions: [],
              error: message,
            })
        })
        return false
      }
    },
    [runsBySessionId, setRunsBySessionId, resolveBackendSessionId, startPolling, getRunCreateFailureMessage, t],
  )

  const retryInterruptedRun = useCallback(async (sessionId: string, runId: string) => {
    const session = sessionsByIdRef.current.get(sessionId)
    const sessionRuns = runsBySessionId[sessionId] ?? []
    const run = sessionRuns.find((candidate) => candidate.run_id === runId) ?? null
    const latestRun = sessionRuns[sessionRuns.length - 1] ?? null
    if (!session || !run) return false
    if (run.status !== 'interrupted') return false
    if (!latestRun || latestRun.run_id !== run.run_id) return false
    if (latestRun.status === 'queued' || latestRun.status === 'running') return false

    try {
      const backendSessionId = await resolveBackendSessionId(sessionId)
      if (!sessionsByIdRef.current.has(sessionId)) return false

      const resp = await copilotApi.createRun(session.novelId, backendSessionId, {
        prompt: run.prompt,
        resume_run_id: run.run_id,
      })
      if (!sessionsByIdRef.current.has(sessionId)) return false

      setRunsBySessionId((prev) => appendSessionRun(prev, sessionId, resp))

      if (resp.status === 'queued' || resp.status === 'running') {
        startPolling(sessionId, session.novelId, backendSessionId, resp.run_id)
      }

      return true
    } catch (error) {
      toast(getRunCreateFailureMessage(error))
      return false
    }
  }, [runsBySessionId, resolveBackendSessionId, setRunsBySessionId, startPolling, toast, getRunCreateFailureMessage])

  // -----------------------------------------------------------------------
  // Apply suggestions
  // -----------------------------------------------------------------------

  const applySuggestions = useCallback(async (sessionId: string, runId: string, suggestionIds: string[]) => {
    const session = sessionsByIdRef.current.get(sessionId)
    const run = (runsBySessionId[sessionId] ?? []).find((candidate) => candidate.run_id === runId) ?? null
    if (!session || !run) return false

    try {
      const backendSessionId = await resolveBackendSessionId(sessionId)
      const resp = await copilotApi.applySuggestions(session.novelId, backendSessionId, run.run_id, suggestionIds)
      if (!sessionsByIdRef.current.has(sessionId)) return false

      const resultByIdMap = new Map(resp.results.map((r) => [r.suggestion_id, r]))
      setRunsBySessionId((prev) => {
        const sessionRuns = prev[sessionId] ?? []
        if (!sessionRuns.some((candidate) => candidate.run_id === run.run_id)) return prev
        return updateSessionRunById(prev, sessionId, run.run_id, (current) => ({
            ...current,
            suggestions: current.suggestions.map((sg) => {
              const result = resultByIdMap.get(sg.suggestion_id)
              if (!result) return sg
              if (result.success) return { ...sg, status: 'applied' as const }
              return sg
            }),
          }))
      })

      const failedResults = resp.results.filter((result) => !result.success)
      if (failedResults.length > 0) {
        toast(getApplyFailureMessage(failedResults[0]))
      }

      const successfulSuggestions = run.suggestions.filter((suggestion) =>
        resultByIdMap.get(suggestion.suggestion_id)?.success,
      )
      invalidateWorldQueriesForAppliedSuggestions(
        queryClient,
        session.novelId,
        successfulSuggestions,
      )
      return resp.results.every((r) => r.success)
    } catch {
      toast(t('copilot.errors.applyFailed'))
      return false
    }
  }, [runsBySessionId, resolveBackendSessionId, setRunsBySessionId, queryClient, toast, getApplyFailureMessage, t])

  // -----------------------------------------------------------------------
  // Dismiss suggestions
  // -----------------------------------------------------------------------

  const dismissSuggestions = useCallback(async (sessionId: string, runId: string, suggestionIds: string[]) => {
    const session = sessionsByIdRef.current.get(sessionId)
    const run = (runsBySessionId[sessionId] ?? []).find((candidate) => candidate.run_id === runId) ?? null
    if (!session || !run) return

    setRunsBySessionId((prev) => {
      const sessionRuns = prev[sessionId] ?? []
      if (!sessionRuns.some((candidate) => candidate.run_id === run.run_id)) return prev
      return updateSessionRunById(prev, sessionId, run.run_id, (current) => ({
          ...current,
          suggestions: current.suggestions.map((sg) =>
            suggestionIds.includes(sg.suggestion_id)
              ? { ...sg, status: 'dismissed' as const }
              : sg,
          ),
        }))
    })

    try {
      const backendSessionId = await resolveBackendSessionId(sessionId)
      await copilotApi.dismissSuggestions(session.novelId, backendSessionId, run.run_id, suggestionIds)
    } catch {
      // Dismiss is intentionally fire-and-forget.
    }
  }, [runsBySessionId, resolveBackendSessionId, setRunsBySessionId])

  return {
    focusedSession,
    activeRun,
    getSessionRun,
    getSessionRuns,
    submitPrompt,
    retryInterruptedRun,
    applySuggestions,
    dismissSuggestions,
  }
}
