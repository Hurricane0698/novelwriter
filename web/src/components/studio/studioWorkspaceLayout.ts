export type StudioRightPanel = 'hidden' | 'assist' | 'copilot' | 'injection-summary'

export function resolveStudioRightPanel(copilotOpen: boolean, summaryOpen: boolean, assistOpen: boolean): StudioRightPanel {
  if (copilotOpen) return 'copilot'
  if (summaryOpen) return 'injection-summary'
  return assistOpen ? 'assist' : 'hidden'
}

export function getStudioWorkspaceLayout(width: number, chaptersOpen: boolean, chapterWidth: number, drawerWidth: number, writing: boolean) {
  const navigationOverlay = width < 760
  const visibleChapterWidth = Math.min(chapterWidth, Math.max(200, width - 48))
  const occupiedChapterWidth = chaptersOpen && !navigationOverlay ? visibleChapterWidth : 0
  const minimumStageWidth = writing ? 640 : 420
  const maxAssistantWidth = Math.max(280, width - occupiedChapterWidth - minimumStageWidth)
  const assistantOverlay = width - occupiedChapterWidth < minimumStageWidth + 280
  const visibleDrawerWidth = Math.min(drawerWidth, assistantOverlay ? Math.max(280, width - 32) : maxAssistantWidth)
  return { navigationOverlay, visibleChapterWidth, maxAssistantWidth, assistantOverlay, visibleDrawerWidth }
}
