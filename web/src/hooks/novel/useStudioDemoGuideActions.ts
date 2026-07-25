import { useCallback } from 'react'
import type { DemoFirstOnboardingStep } from '@/lib/demoFirstOnboardingStorage'

interface UseStudioDemoGuideActionsArgs {
  visitDemoGuideStep: (step: DemoFirstOnboardingStep) => void
  openManualDemoGuide: () => void
  openDemoChapter: () => void
  openDemoWriteStage: () => void
  openDemoAtlas: () => void
  openDemoCopilot: () => void
}

export function useStudioDemoGuideActions({
  visitDemoGuideStep,
  openManualDemoGuide,
  openDemoChapter,
  openDemoWriteStage,
  openDemoAtlas,
  openDemoCopilot,
}: UseStudioDemoGuideActionsArgs) {
  const handleReopenDemoGuide = useCallback(() => {
    openManualDemoGuide()
  }, [openManualDemoGuide])

  const handleOpenDemoChapter = useCallback(() => {
    visitDemoGuideStep('chapter')
    openDemoChapter()
  }, [openDemoChapter, visitDemoGuideStep])

  const handleOpenDemoWriteStage = useCallback(() => {
    visitDemoGuideStep('write')
    openDemoWriteStage()
  }, [openDemoWriteStage, visitDemoGuideStep])

  const handleOpenDemoAtlas = useCallback(() => {
    visitDemoGuideStep('atlas')
    openDemoAtlas()
  }, [openDemoAtlas, visitDemoGuideStep])

  const handleOpenDemoCopilot = useCallback(() => {
    visitDemoGuideStep('copilot')
    openDemoCopilot()
  }, [openDemoCopilot, visitDemoGuideStep])

  return {
    handleReopenDemoGuide,
    handleOpenDemoChapter,
    handleOpenDemoWriteStage,
    handleOpenDemoAtlas,
    handleOpenDemoCopilot,
  }
}
