import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { countVisitedDemoFirstWritingOnboardingSteps } from '@/lib/demoFirstOnboardingStorage'
import { useDemoFirstGuideAnalytics } from '@/hooks/novel/useDemoFirstGuideAnalytics'
import { useDemoFirstGuideStorageState } from '@/hooks/novel/useDemoFirstGuideStorageState'

const { mockTrackHostedAnalyticsEvent } = vi.hoisted(() => ({
  mockTrackHostedAnalyticsEvent: vi.fn(),
}))

vi.mock('@/lib/hostedAnalytics', () => ({
  trackHostedAnalyticsEvent: (...args: unknown[]) => mockTrackHostedAnalyticsEvent(...args),
}))

describe('useDemoFirstGuideAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockTrackHostedAnalyticsEvent.mockResolvedValue(undefined)
  })

  it('tracks demo-guide views and auto-visits the write step', async () => {
    const { result } = renderHook(() => {
      const storage = useDemoFirstGuideStorageState({
        novelId: 7,
        createdAt: '2026-03-01T00:00:00Z',
      })
      const analytics = useDemoFirstGuideAnalytics({
        novelId: 7,
        isDemoNovel: true,
        demoGuideStorageKey: storage.demoGuideStorageKey,
        demoGuideState: storage.demoGuideState,
        demoGuideProgressCount: countVisitedDemoFirstWritingOnboardingSteps(storage.demoGuideState),
        forceOpenDemoGuide: false,
        showDemoGuideExpanded: true,
        activeStage: 'write',
        activeChapterNum: 3,
        chapterLoading: false,
        showWorkbenchRail: false,
        markStepVisited: storage.markStepVisited,
        skipDemoGuide: storage.skipDemoGuide,
        closeManualDemoGuide: storage.closeManualDemoGuide,
      })

      return {
        ...storage,
        ...analytics,
      }
    })

    await waitFor(() => {
      expect(result.current.demoGuideState.visited.write).toBe(true)
    })

    expect(mockTrackHostedAnalyticsEvent).toHaveBeenCalledWith('demo_guide_view', {
      novelId: 7,
      meta: {
        source: 'auto',
        status: 'not_started',
        progress_count: 0,
      },
    })
    expect(mockTrackHostedAnalyticsEvent).toHaveBeenCalledWith('demo_guide_step_complete', {
      novelId: 7,
      meta: {
        step: 'write',
        progress_count: 1,
      },
    })
  })

  it('tracks skip and closes the manual reopen state', () => {
    const { result } = renderHook(() => {
      const storage = useDemoFirstGuideStorageState({
        novelId: 7,
        createdAt: '2026-03-01T00:00:00Z',
      })
      const analytics = useDemoFirstGuideAnalytics({
        novelId: 7,
        isDemoNovel: true,
        demoGuideStorageKey: storage.demoGuideStorageKey,
        demoGuideState: storage.demoGuideState,
        demoGuideProgressCount: countVisitedDemoFirstWritingOnboardingSteps(storage.demoGuideState),
        forceOpenDemoGuide: true,
        showDemoGuideExpanded: true,
        activeStage: 'entity',
        activeChapterNum: null,
        chapterLoading: false,
        showWorkbenchRail: false,
        markStepVisited: storage.markStepVisited,
        skipDemoGuide: storage.skipDemoGuide,
        closeManualDemoGuide: storage.closeManualDemoGuide,
      })

      return {
        ...storage,
        ...analytics,
      }
    })

    act(() => {
      result.current.openManualDemoGuide()
    })
    expect(result.current.manualForceOpenDemoGuide).toBe(true)

    act(() => {
      result.current.handleSkipDemoGuide()
    })

    expect(result.current.manualForceOpenDemoGuide).toBe(false)
    expect(result.current.demoGuideState.status).toBe('skipped')
    expect(mockTrackHostedAnalyticsEvent).toHaveBeenCalledWith('demo_guide_skipped', {
      novelId: 7,
      meta: {
        progress_count: 0,
      },
    })
  })
})
