import { useCallback, useRef, useState } from 'react'
import {
  buildCopilotSessionSignature,
  normalizeCopilotInteractionLocale,
  type CopilotPrefill,
  type OpenNovelCopilotOptions,
  type NovelCopilotSession,
} from '@/types/copilot'
import { getDefaultCopilotSessionTitle } from '@/components/novel-copilot/novelCopilotHelpers'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { copilotApi } from '@/services/api'

export interface NovelCopilotSessionsOnlyState {
  composerDrafts: Record<string, string>
  setComposerDraft: (sessionId: string, text: string) => void
  isOpen: boolean
  sessions: NovelCopilotSession[]
  focusedSessionId: string | null
  openDrawer: (prefill: CopilotPrefill, options?: OpenNovelCopilotOptions) => string
  focusSession: (sessionId: string) => void
  removeSession: (sessionId: string) => void
  closeDrawer: () => void
  reopenDrawer: () => void
  resolveBackendSessionId: (sessionId: string) => Promise<string>
}

function buildLocalSessionId() {
  return `ncs_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

interface BackendSessionRequestState {
  key: string
  promise: Promise<string>
}

function buildOpenSessionRequest(session: NovelCopilotSession) {
  return {
    mode: session.prefill.mode,
    scope: session.prefill.scope,
    context: session.prefill.context,
    interaction_locale: session.interactionLocale,
    display_title: session.displayTitle,
  }
}

function buildOpenSessionRequestKey(session: NovelCopilotSession) {
  return JSON.stringify({
    novel_id: session.novelId,
    ...buildOpenSessionRequest(session),
  })
}

interface UseNovelCopilotSessionsStateParams {
  novelId: number | null
  interactionLocale: string
}

export function useNovelCopilotSessionsState({
  novelId,
  interactionLocale,
}: UseNovelCopilotSessionsStateParams): NovelCopilotSessionsOnlyState {
  const [isOpen, setIsOpen] = useState(false)
  const [composerDrafts, setComposerDrafts] = useState<Record<string, string>>({})
  const setComposerDraft = useCallback((sessionId: string, text: string) => {
    setComposerDrafts(current => ({ ...current, [sessionId]: text }))
  }, [])
  const [sessions, setSessions] = useState<NovelCopilotSession[]>([])
  const [focusedSessionId, setFocusedSessionId] = useState<string | null>(null)
  const sessionsRef = useRef<NovelCopilotSession[]>([])
  const backendSessionRequestsRef = useRef<Record<string, BackendSessionRequestState>>({})
  const syncedOpenSessionKeysRef = useRef<Record<string, string>>({})
  const normalizedInteractionLocale = normalizeCopilotInteractionLocale(interactionLocale)

  const commitSessions = useCallback((nextSessions: NovelCopilotSession[]) => {
    sessionsRef.current = nextSessions
    const activeSessionIds = new Set(nextSessions.map((session) => session.sessionId))
    Object.keys(backendSessionRequestsRef.current).forEach((sessionId) => {
      if (!activeSessionIds.has(sessionId)) delete backendSessionRequestsRef.current[sessionId]
    })
    Object.keys(syncedOpenSessionKeysRef.current).forEach((sessionId) => {
      if (!activeSessionIds.has(sessionId)) delete syncedOpenSessionKeysRef.current[sessionId]
    })
    setSessions(nextSessions)
  }, [])

  const setSessionBackendSessionId = useCallback((sessionId: string, backendSessionId: string) => {
    const currentSessions = sessionsRef.current
    let changed = false

    const nextSessions = currentSessions.map((session) => {
      if (session.sessionId !== sessionId || session.backendSessionId === backendSessionId) {
        return session
      }
      changed = true
      return { ...session, backendSessionId }
    })

    if (changed) commitSessions(nextSessions)
  }, [commitSessions])

  const resolveBackendSessionId = useCallback((sessionId: string): Promise<string> => {
    const session = sessionsRef.current.find((candidate) => candidate.sessionId === sessionId)
    if (!session) return Promise.reject(new Error(`Session ${sessionId} not found`))

    const requestKey = buildOpenSessionRequestKey(session)
    const syncedKey = syncedOpenSessionKeysRef.current[sessionId]
    if (session.backendSessionId && syncedKey === requestKey) {
      return Promise.resolve(session.backendSessionId)
    }

    const inflightRequest = backendSessionRequestsRef.current[sessionId]
    if (inflightRequest && inflightRequest.key === requestKey) {
      return inflightRequest.promise
    }

    const promise = copilotApi.openSession(session.novelId, buildOpenSessionRequest(session))
      .then((resp) => {
        const currentSession = sessionsRef.current.find((candidate) => candidate.sessionId === sessionId)
        if (!currentSession) return resp.session_id

        setSessionBackendSessionId(sessionId, resp.session_id)

        if (buildOpenSessionRequestKey(currentSession) === requestKey) {
          syncedOpenSessionKeysRef.current[sessionId] = requestKey
        }

        return resp.session_id
      })
      .finally(() => {
        const currentRequest = backendSessionRequestsRef.current[sessionId]
        if (currentRequest?.promise === promise) {
          delete backendSessionRequestsRef.current[sessionId]
        }
      })

    backendSessionRequestsRef.current[sessionId] = {
      key: requestKey,
      promise,
    }

    return promise
  }, [setSessionBackendSessionId])

  const prefetchBackendSession = useCallback((sessionId: string) => {
    void resolveBackendSessionId(sessionId).catch(() => {
      // Best-effort warmup only. Prompt submission resolves backend session again if needed.
    })
  }, [resolveBackendSessionId])

  const openDrawer = useCallback((prefill: CopilotPrefill, options?: OpenNovelCopilotOptions) => {
    if (novelId == null) return ''

    const currentSessions = sessionsRef.current
    const signature = buildCopilotSessionSignature(prefill, novelId, normalizedInteractionLocale)
    const displayTitle = options?.displayTitle?.trim() || getDefaultCopilotSessionTitle(prefill)
    const existing = currentSessions.find((session) => session.signature === signature)

    if (existing) {
      const nextExistingSession = {
        ...existing,
        prefill,
        displayTitle,
      }

      if (
        existing.displayTitle !== displayTitle
        || existing.prefill !== prefill
      ) {
        commitSessions(
          currentSessions.map((session) =>
            session.sessionId === existing.sessionId
              ? nextExistingSession
              : session,
          ),
        )
      }
      setFocusedSessionId(existing.sessionId)
      setIsOpen(true)
      void trackHostedAnalyticsEvent('copilot_open', {
        novelId,
        meta: {
          mode: existing.prefill.mode,
          scope: existing.prefill.scope,
          surface: existing.prefill.context?.surface ?? 'unknown',
        },
      })
      prefetchBackendSession(existing.sessionId)
      return existing.sessionId
    }

    const localId = buildLocalSessionId()
    const nextSession: NovelCopilotSession = {
      sessionId: localId,
      signature,
      prefill,
      displayTitle,
      novelId,
      interactionLocale: normalizedInteractionLocale,
      backendSessionId: null,
    }

    commitSessions([...currentSessions, nextSession])
    setFocusedSessionId(localId)
    setIsOpen(true)
    void trackHostedAnalyticsEvent('copilot_open', {
      novelId,
      meta: {
        mode: nextSession.prefill.mode,
        scope: nextSession.prefill.scope,
        surface: nextSession.prefill.context?.surface ?? 'unknown',
      },
    })
    prefetchBackendSession(localId)
    return localId
  }, [commitSessions, novelId, normalizedInteractionLocale, prefetchBackendSession])

  const focusSession = useCallback((sessionId: string) => {
    setFocusedSessionId(sessionId)
    setIsOpen(true)
  }, [])

  const removeSession = useCallback((sessionId: string) => {
    const currentSessions = sessionsRef.current
    const currentIndex = currentSessions.findIndex((session) => session.sessionId === sessionId)
    if (currentIndex === -1) return

    const nextSessions = currentSessions.filter((session) => session.sessionId !== sessionId)
    commitSessions(nextSessions)
    setComposerDrafts(current => {
      const next = { ...current }
      delete next[sessionId]
      return next
    })

    setFocusedSessionId((prevFocusedSessionId) => {
      if (prevFocusedSessionId !== sessionId) return prevFocusedSessionId

      const fallback =
        nextSessions[currentIndex] ??
        nextSessions[currentIndex - 1] ??
        nextSessions[0] ??
        null

      if (!fallback) {
        setIsOpen(false)
        return null
      }

      return fallback.sessionId
    })
  }, [commitSessions])

  const closeDrawer = useCallback(() => {
    setIsOpen(false)
  }, [])

  const reopenDrawer = useCallback(() => {
    if (sessionsRef.current.length > 0) setIsOpen(true)
  }, [])

  return {
    composerDrafts,
    setComposerDraft,
    isOpen,
    sessions,
    focusedSessionId,
    openDrawer,
    focusSession,
    removeSession,
    closeDrawer,
    reopenDrawer,
    resolveBackendSessionId,
  }
}
