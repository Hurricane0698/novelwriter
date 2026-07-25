import { useCallback, useEffect, useRef } from 'react'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'
import {
  countVisitedDemoFirstWritingOnboardingSteps,
  type DemoFirstOnboardingStep,
  type DemoFirstWritingOnboardingState,
} from '@/lib/demoFirstOnboardingStorage'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import type { DemoFirstGuideStateTransition } from './useDemoFirstGuideStorageState'

interface UseDemoFirstGuideAnalyticsArgs {
  novelId: number
  isDemoNovel: boolean
  demoGuideStorageKey: string
  demoGuideState: DemoFirstWritingOnboardingState
  demoGuideProgressCount: number
  forceOpenDemoGuide: boolean
  showDemoGuideExpanded: boolean
  activeStage: NovelShellStage
  activeChapterNum: number | null
  chapterLoading: boolean
  showWorkbenchRail: boolean
  markStepVisited: (step: DemoFirstOnboardingStep) => DemoFirstGuideStateTransition
  skipDemoGuide: () => DemoFirstGuideStateTransition
  closeManualDemoGuide: () => void
}

export function useDemoFirstGuideAnalytics({
  novelId,
  isDemoNovel,
  demoGuideStorageKey,
  demoGuideState,
  demoGuideProgressCount,
  forceOpenDemoGuide,
  showDemoGuideExpanded,
  activeStage,
  activeChapterNum,
  chapterLoading,
  showWorkbenchRail,
  markStepVisited,
  skipDemoGuide,
  closeManualDemoGuide,
}: UseDemoFirstGuideAnalyticsArgs) {
  const trackedDemoGuideViewRef = useRef(false)
  const scheduledAutoDemoGuideStepRef = useRef<Partial<Record<DemoFirstOnboardingStep, string>>>({})

  const trackVisitTransition = useCallback((transition: DemoFirstGuideStateTransition, step: DemoFirstOnboardingStep) => {
    if (!isDemoNovel) return

    const nextProgressCount = countVisitedDemoFirstWritingOnboardingSteps(transition.next)
    if (!transition.previous.visited[step] && transition.next.visited[step]) {
      void trackHostedAnalyticsEvent('demo_guide_step_complete', {
        novelId,
        meta: {
          step,
          progress_count: nextProgressCount,
        },
      })
    }

    if (transition.previous.status !== 'completed' && transition.next.status === 'completed') {
      void trackHostedAnalyticsEvent('demo_guide_completed', {
        novelId,
        meta: {
          progress_count: nextProgressCount,
        },
      })
      closeManualDemoGuide()
    }
  }, [closeManualDemoGuide, isDemoNovel, novelId])

  const visitDemoGuideStep = useCallback((step: DemoFirstOnboardingStep) => {
    const transition = markStepVisited(step)
    trackVisitTransition(transition, step)
  }, [markStepVisited, trackVisitTransition])

  const handleSkipDemoGuide = useCallback(() => {
    const transition = skipDemoGuide()
    if (isDemoNovel && transition.previous.status !== 'skipped') {
      void trackHostedAnalyticsEvent('demo_guide_skipped', {
        novelId,
        meta: {
          progress_count: countVisitedDemoFirstWritingOnboardingSteps(transition.next),
        },
      })
    }
    closeManualDemoGuide()
  }, [closeManualDemoGuide, isDemoNovel, novelId, skipDemoGuide])

  useEffect(() => {
    if (!showDemoGuideExpanded) {
      trackedDemoGuideViewRef.current = false
      return
    }
    if (trackedDemoGuideViewRef.current) return
    trackedDemoGuideViewRef.current = true
    void trackHostedAnalyticsEvent('demo_guide_view', {
      novelId,
      meta: {
        source: forceOpenDemoGuide ? 'reopen' : 'auto',
        status: demoGuideState.status,
        progress_count: demoGuideProgressCount,
      },
    })
  }, [demoGuideProgressCount, demoGuideState.status, forceOpenDemoGuide, novelId, showDemoGuideExpanded])

  const scheduleAutoVisitDemoGuideStep = useCallback((step: DemoFirstOnboardingStep) => {
    const marker = `${demoGuideStorageKey}:${step}`
    if (scheduledAutoDemoGuideStepRef.current[step] === marker) return
    scheduledAutoDemoGuideStepRef.current[step] = marker
    queueMicrotask(() => {
      if (scheduledAutoDemoGuideStepRef.current[step] !== marker) return
      visitDemoGuideStep(step)
    })
  }, [demoGuideStorageKey, visitDemoGuideStep])

  useEffect(() => {
    if (!isDemoNovel || activeStage !== 'chapter' || activeChapterNum === null || chapterLoading) {
      scheduledAutoDemoGuideStepRef.current.chapter = undefined
      return
    }
    if (demoGuideState.visited.chapter) {
      scheduledAutoDemoGuideStepRef.current.chapter = undefined
      return
    }
    scheduleAutoVisitDemoGuideStep('chapter')
  }, [
    activeChapterNum,
    activeStage,
    chapterLoading,
    demoGuideState.visited.chapter,
    isDemoNovel,
    scheduleAutoVisitDemoGuideStep,
  ])

  useEffect(() => {
    if (!isDemoNovel || activeStage !== 'write') {
      scheduledAutoDemoGuideStepRef.current.write = undefined
      return
    }
    if (demoGuideState.visited.write) {
      scheduledAutoDemoGuideStepRef.current.write = undefined
      return
    }
    scheduleAutoVisitDemoGuideStep('write')
  }, [activeStage, demoGuideState.visited.write, isDemoNovel, scheduleAutoVisitDemoGuideStep])

  useEffect(() => {
    if (!isDemoNovel || !showWorkbenchRail) {
      scheduledAutoDemoGuideStepRef.current.copilot = undefined
      return
    }
    if (demoGuideState.visited.copilot) {
      scheduledAutoDemoGuideStepRef.current.copilot = undefined
      return
    }
    scheduleAutoVisitDemoGuideStep('copilot')
  }, [demoGuideState.visited.copilot, isDemoNovel, scheduleAutoVisitDemoGuideStep, showWorkbenchRail])

  return {
    visitDemoGuideStep,
    handleSkipDemoGuide,
  }
}
