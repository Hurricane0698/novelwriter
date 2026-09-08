import { useMemo, type ReactNode } from 'react'
import '@/lib/uiMessagePacks/copilot'
import {
  getDefaultCopilotInteractionLocale,
  normalizeCopilotInteractionLocale,
} from '@/types/copilot'
import { useNovelCopilotSessionsState } from '@/hooks/novel-copilot/useNovelCopilotSessions'
import {
  useNovelCopilotRuns,
  useNovelCopilotRunsState,
} from '@/hooks/novel-copilot/useNovelCopilotRuns'
import { NovelCopilotContext } from './NovelCopilotContext'

export function NovelCopilotProvider({
  children,
  novelId = null,
  interactionLocale,
}: {
  children: ReactNode
  novelId?: number | null
  interactionLocale?: string
}) {
  const effectiveInteractionLocale = normalizeCopilotInteractionLocale(
    interactionLocale ?? getDefaultCopilotInteractionLocale(),
  )
  const sessionsState = useNovelCopilotSessionsState({
    novelId,
    interactionLocale: effectiveInteractionLocale,
  })
  const runsState = useNovelCopilotRunsState(sessionsState.sessions)
  const controllerState = useNovelCopilotRuns({
    sessions: sessionsState.sessions,
    focusedSessionId: sessionsState.focusedSessionId,
    runsBySessionId: runsState.runsBySessionId,
    setRunsBySessionId: runsState.setRunsBySessionId,
    resolveBackendSessionId: sessionsState.resolveBackendSessionId,
  })

  const value = useMemo(() => ({
    ...sessionsState,
    ...controllerState,
  }), [sessionsState, controllerState])

  return (
    <NovelCopilotContext.Provider value={value}>
      {children}
    </NovelCopilotContext.Provider>
  )
}
