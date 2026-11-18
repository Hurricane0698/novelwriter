import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import type { CopilotTextTarget, TextTargetBinding, TextChange } from '@/types/copilot'
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
    getLocalSession: sessionsState.getLocalSession,
    focusedSessionId: sessionsState.focusedSessionId,
    runsBySessionId: runsState.runsBySessionId,
    setRunsBySessionId: runsState.setRunsBySessionId,
    resolveBackendSessionId: sessionsState.resolveBackendSessionId,
  })

  const textTargets = useRef(new Map<string, TextTargetBinding>())
  const [textUndo, setTextUndo] = useState<{ runId: string; change: TextChange } | null>(null)
  const registerTextTarget = useCallback((target: CopilotTextTarget, binding: TextTargetBinding) => {
    const key = `${target.kind}:${target.id}`
    textTargets.current.set(key, binding)
    return () => { if (textTargets.current.get(key) === binding) textTargets.current.delete(key) }
  }, [])
  const getTextTarget = useCallback((target: CopilotTextTarget) => textTargets.current.get(`${target.kind}:${target.id}`), [])

  const value = useMemo(() => ({
    ...sessionsState,
    ...controllerState,
    registerTextTarget, getTextTarget, textUndo, setTextUndo,
  }), [sessionsState, controllerState, registerTextTarget, getTextTarget, textUndo])

  return (
    <NovelCopilotContext.Provider value={value}>
      {children}
    </NovelCopilotContext.Provider>
  )
}
