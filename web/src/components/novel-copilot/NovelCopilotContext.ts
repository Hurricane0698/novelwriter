import { createContext, useContext } from 'react'
import type { NovelCopilotSessionsOnlyState } from '@/hooks/novel-copilot/useNovelCopilotSessions'
import type { NovelCopilotRunControllerState } from '@/hooks/novel-copilot/useNovelCopilotRuns'

export type NovelCopilotState = NovelCopilotSessionsOnlyState & NovelCopilotRunControllerState

export const NovelCopilotContext = createContext<NovelCopilotState | null>(null)

export function useNovelCopilot() {
  const context = useContext(NovelCopilotContext)
  if (!context) {
    throw new Error('useNovelCopilot must be used within a NovelCopilotProvider')
  }
  return context
}
