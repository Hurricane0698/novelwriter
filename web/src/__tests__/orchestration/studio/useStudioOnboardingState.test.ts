import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LABELS } from '@/constants/labels'
import { useStudioOnboardingState } from '@/hooks/novel/useStudioOnboardingState'
import type { BootstrapJobResponse, Novel } from '@/types/api'

const {
  mockTrackHostedAnalyticsEvent,
  mockGetLlmApiErrorMessage,
  MockApiError,
} = vi.hoisted(() => {
  class HoistedMockApiError extends Error {
    status?: number
    code?: string

    constructor(status?: number, code?: string) {
      super('api error')
      this.status = status
      this.code = code
    }
  }

  return {
    mockTrackHostedAnalyticsEvent: vi.fn(),
    mockGetLlmApiErrorMessage: vi.fn(),
    MockApiError: HoistedMockApiError,
  }
})

vi.mock('@/lib/hostedAnalytics', () => ({
  trackHostedAnalyticsEvent: (...args: unknown[]) => mockTrackHostedAnalyticsEvent(...args),
}))

vi.mock('@/lib/llmErrorMessages', () => ({
  getLlmApiErrorMessage: (...args: unknown[]) => mockGetLlmApiErrorMessage(...args),
}))

vi.mock('@/services/api', () => ({
  ApiError: MockApiError,
}))

function buildNovel(partial?: Partial<Novel>): Novel {
  return {
    id: 7,
    title: '测试小说',
    author: '作者',
    language: 'zh',
    total_chapters: 3,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    ...partial,
  }
}

function buildBootstrapJob(partial?: Partial<BootstrapJobResponse>): BootstrapJobResponse {
  return {
    job_id: 11,
    novel_id: 7,
    mode: 'initial',
    initialized: false,
    status: 'pending',
    progress: {
      step: 0,
      detail: 'queued',
    },
    result: {
      entities_found: 0,
      relationships_found: 0,
      index_refresh_only: false,
    },
    error: null,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    ...partial,
  }
}

function buildArgs(overrides?: Partial<Parameters<typeof useStudioOnboardingState>[0]>) {
  return {
    novelId: 7,
    novel: buildNovel(),
    locale: 'zh',
    t: (key: string) => key,
    searchParams: new URLSearchParams('stage=entity&chapter=3'),
    activeStage: 'entity' as const,
    activeChapterNum: 3,
    chapterLoading: false,
    showWorkbenchRail: false,
    worldEntityCount: 1,
    worldSystemCount: 0,
    worldLoading: false,
    bootstrapLoading: false,
    bootstrapJob: null,
    bootstrapTriggerPending: false,
    triggerInitialBootstrap: vi.fn(),
    openDemoChapter: vi.fn(),
    openDemoWriteStage: vi.fn(),
    openDemoAtlas: vi.fn(),
    openDemoCopilot: vi.fn(),
    dismissWorldOnboardingRoute: vi.fn(),
    ...overrides,
  }
}

describe('useStudioOnboardingState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockTrackHostedAnalyticsEvent.mockResolvedValue(undefined)
    mockGetLlmApiErrorMessage.mockReturnValue(null)
  })

  it('shows the empty-world onboarding when Studio has no world data and no active bootstrap', async () => {
    const { result } = renderHook(() => useStudioOnboardingState(buildArgs({
      worldEntityCount: 0,
      worldSystemCount: 0,
    })))

    expect(result.current.showWorldOnboarding).toBe(true)
    expect(result.current.preparationGate).toBeNull()

    await waitFor(() => {
      expect(mockTrackHostedAnalyticsEvent).toHaveBeenCalledWith('world_onboarding_view', {
        novelId: 7,
        meta: { surface: 'studio' },
      })
    })
  })

  it('does not surface empty-world onboarding while deferred auto-bootstrap is still pending', async () => {
    const { result } = renderHook(() => useStudioOnboardingState(buildArgs({
      worldEntityCount: 0,
      worldSystemCount: 0,
      novel: buildNovel({
        window_index: {
          status: 'missing',
          revision: 2,
          built_revision: null,
          error: null,
          readiness: 'processing',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: true,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: 2048,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'deferred',
            bootstrap_plan: 'defer_until_index',
            readiness_mode: 'degraded_target',
            error: null,
          },
          job: {
            status: 'running',
            target_revision: 2,
            completed_revision: null,
            error: null,
            created_at: null,
            started_at: null,
            finished_at: null,
            metrics: null,
          },
        },
      }),
    })))

    expect(result.current.showWorldOnboarding).toBe(false)
    expect(result.current.preparationGate).toMatchObject({
      title: 'studio.preparation.title',
      description: 'studio.preparation.bootstrapDescription',
    })

    await waitFor(() => {
      expect(mockTrackHostedAnalyticsEvent).not.toHaveBeenCalledWith('world_onboarding_view', expect.anything())
    })
  })

  it('collapses a completed demo guide into the reopen affordance unless the URL forces it open', () => {
    localStorage.setItem(
      'novwr_demo_first_onboarding_dismissed_7_2026-03-01T00:00:00Z',
      JSON.stringify({
        version: 2,
        status: 'completed',
        visited: {
          chapter: true,
          atlas: true,
          write: true,
          copilot: true,
        },
      }),
    )

    const { result: defaultResult } = renderHook(() => useStudioOnboardingState(buildArgs({
      novel: buildNovel({ is_seeded_demo: true }),
    })))

    expect(defaultResult.current.showDemoGuideExpanded).toBe(false)
    expect(defaultResult.current.showDemoGuideReopen).toBe(true)

    const { result: forcedOpenResult } = renderHook(() => useStudioOnboardingState(buildArgs({
      novel: buildNovel({ is_seeded_demo: true }),
      searchParams: new URLSearchParams('stage=entity&chapter=3&demoGuide=open'),
    })))

    expect(forcedOpenResult.current.showDemoGuideExpanded).toBe(true)
    expect(forcedOpenResult.current.showDemoGuideReopen).toBe(false)
  })

  it('marks demo-guide steps in storage and forwards the matching navigation callback', () => {
    const openDemoWriteStage = vi.fn()

    const { result } = renderHook(() => useStudioOnboardingState(buildArgs({
      novel: buildNovel({ is_seeded_demo: true }),
      openDemoWriteStage,
    })))

    act(() => {
      result.current.handleOpenDemoWriteStage()
    })

    expect(openDemoWriteStage).toHaveBeenCalledTimes(1)
    expect(JSON.parse(localStorage.getItem('novwr_demo_first_onboarding_dismissed_7_2026-03-01T00:00:00Z') ?? '{}')).toMatchObject({
      status: 'in_progress',
      visited: {
        write: true,
      },
    })
  })

  it('maps bootstrap trigger errors onto the onboarding error state', () => {
    const triggerInitialBootstrap = vi.fn((handlers?: { onError?: (error: unknown) => void }) => {
      handlers?.onError?.(new MockApiError(400, 'bootstrap_no_text'))
    })

    const { result } = renderHook(() => useStudioOnboardingState(buildArgs({
      worldEntityCount: 0,
      worldSystemCount: 0,
      novel: buildNovel({
        is_seeded_demo: false,
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          ingest: null,
          job: null,
        },
      }),
      triggerInitialBootstrap,
      bootstrapJob: buildBootstrapJob({ status: 'failed', error: null }),
    })))

    act(() => {
      result.current.handleTriggerBootstrap()
    })

    expect(triggerInitialBootstrap).toHaveBeenCalledTimes(1)
    expect(result.current.bootstrapError).toBe(LABELS.BOOTSTRAP_NO_TEXT)
  })
})
