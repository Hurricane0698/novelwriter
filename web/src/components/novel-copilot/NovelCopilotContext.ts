import { createContext, useContext } from 'react'
import type { NovelCopilotSessionsOnlyState } from '@/hooks/novel-copilot/useNovelCopilotSessions'
import type { NovelCopilotRunControllerState } from '@/hooks/novel-copilot/useNovelCopilotRuns'
import type { CopilotTextTarget, TextTargetBinding, TextChange } from '@/types/copilot'

export type NovelCopilotState = NovelCopilotSessionsOnlyState & NovelCopilotRunControllerState & {
  registerTextTarget: (target: CopilotTextTarget, binding: TextTargetBinding) => () => void
  getTextTarget: (target: CopilotTextTarget) => TextTargetBinding | undefined
  textUndo: { runId: string; change: TextChange } | null
  setTextUndo: (undo: { runId: string; change: TextChange } | null) => void
}

export const NovelCopilotContext = createContext<NovelCopilotState | null>(null)

export function useNovelCopilot() {
  const context = useContext(NovelCopilotContext)
  if (!context) {
    throw new Error('useNovelCopilot must be used within a NovelCopilotProvider')
  }
  return context
}
