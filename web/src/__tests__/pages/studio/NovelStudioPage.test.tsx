import type { ReactNode } from 'react'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { NovelShell } from '@/components/novel-shell/NovelShell'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { novelKeys } from '@/hooks/novel/keys'
import { NovelStudioPage } from '@/pages/NovelStudioPage'
import { createTestQueryClient } from '@/__tests__/support/queryClient'

const ACTIVE_PENDING_STARTED_AT = Date.parse('2026-03-30T00:00:30Z')
const ACTIVE_PENDING_NOW_MS = Date.parse('2026-03-30T00:10:00Z')

const mockUseUpdateChapter = vi.fn()
const mockUseCreateChapter = vi.fn()
const mockUseDeleteChapter = vi.fn()
const mockUseWorldEntities = vi.fn()
const mockUseWorldSystems = vi.fn()
const mockUseBootstrapStatus = vi.fn()
const mockUseTriggerBootstrap = vi.fn()
const mockUseDebouncedAutoSave = vi.fn()
const mockUseContinuationSetupState = vi.fn()
const mockReadGenerationResultsDebug = vi.fn()
const mockLoadAtlasAssistWorkbench = vi.fn()
const mockScheduleAtlasAssistWorkbenchPrefetch = vi.fn()

function buildNovelResponse(overrides?: Record<string, unknown>) {
  return {
    id: 7,
    title: '测试小说',
    is_seeded_demo: false,
    total_chapters: 3,
    created_at: '2026-03-01T00:00:00Z',
    ...overrides,
  }
}

vi.mock('@/components/layout/PageShell', () => ({
  PageShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/NovelShellLayout', () => ({
  NovelShellLayout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/NovelShellRail', () => ({
  NovelShellRail: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/ArtifactStage', () => ({
  ArtifactStage: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/detail/ChapterContent', () => ({
  ChapterContent: ({
    content,
    isLoading,
  }: {
    content: string | null
    isLoading: boolean
  }) => <div>{isLoading ? '加载章节中' : content}</div>,
}))

vi.mock('@/components/detail/ChapterEditor', () => ({
  ChapterEditor: () => <div data-testid="chapter-editor" />,
}))

vi.mock('@/components/detail/EmptyWorldOnboarding', () => ({
  EmptyWorldOnboarding: () => <div data-testid="world-onboarding" />,
}))

vi.mock('@/components/detail/DemoFirstWritingOnboarding', () => ({
  DemoFirstWritingOnboarding: () => <div data-testid="demo-first-onboarding" />,
}))

vi.mock('@/components/world-model/shared/WorldGenerationDialog', () => ({
  WorldGenerationDialog: ({
    open,
    onGenerateSuccess,
  }: {
    open?: boolean
    onGenerateSuccess?: (response: {
      entities_created: number
      relationships_created: number
      systems_created: number
      warnings: []
    }) => void
  }) => (
    open ? (
      <button
        type="button"
        data-testid="mock-world-gen-success"
        onClick={() => onGenerateSuccess?.({
          entities_created: 1,
          relationships_created: 0,
          systems_created: 1,
          warnings: [],
        })}
      >
        world-gen-success
      </button>
    ) : null
  ),
}))

vi.mock('@/components/ui/glass-surface', () => ({
  GlassSurface: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/generation/DriftWarningPopover', () => ({
  DriftWarningPopover: () => null,
}))

vi.mock('@/components/world-model/shared/BootstrapPanel', () => ({
  BootstrapPanel: ({
    onLifecycleChange,
    onTriggerStart,
    onJobAccepted,
  }: {
    onLifecycleChange?: (state: unknown) => void
    onTriggerStart?: (startedAtMs: number) => void
    onJobAccepted?: (job: { job_id: number }, startedAtMs: number) => void
  }) => (
    <div data-testid="bootstrap-panel">
      <button
        type="button"
        data-testid="mock-bootstrap-start"
        onClick={() => onTriggerStart?.(ACTIVE_PENDING_STARTED_AT)}
      >
        bootstrap-start
      </button>
      <button
        type="button"
        data-testid="mock-bootstrap-accepted"
        onClick={() => onJobAccepted?.({ job_id: 41 }, ACTIVE_PENDING_STARTED_AT)}
      >
        bootstrap-accepted
      </button>
      <button
        type="button"
        data-testid="mock-bootstrap-complete"
        onClick={() => onLifecycleChange?.({
          phase: 'completed',
          summary: '2 实体 · 1 关系',
          requiresReview: true,
          entityCount: 2,
          relationshipCount: 1,
        })}
      >
        bootstrap-complete
      </button>
    </div>
  ),
}))

vi.mock('@/components/studio/panels/InjectionSummaryPanel', () => ({
  InjectionSummaryPanel: () => <div data-testid="injection-summary-panel" />,
}))

vi.mock('@/components/studio/stages/ContinuationSetupStage', () => ({
  ContinuationSetupStage: () => <div data-testid="continuation-setup" />,
}))

vi.mock('@/components/studio/stages/StudioEntityStage', () => ({
  StudioEntityStage: () => <div data-testid="studio-entity-stage" />,
}))

vi.mock('@/components/studio/stages/StudioDraftReviewStage', () => ({
  StudioDraftReviewStage: () => <div data-testid="studio-review-stage" />,
}))

vi.mock('@/components/studio/stages/StudioEntityStage.tsx', () => ({
  StudioEntityStage: () => <div data-testid="studio-entity-stage" />,
}))

vi.mock('@/components/studio/stages/StudioDraftReviewStage.tsx', () => ({
  StudioDraftReviewStage: () => <div data-testid="studio-review-stage" />,
}))

vi.mock('@/components/studio/stages/StudioRelationshipStage', () => ({
  StudioRelationshipStage: () => <div data-testid="studio-relationship-stage" />,
}))

vi.mock('@/components/studio/stages/StudioSystemStage', () => ({
  StudioSystemStage: () => <div data-testid="studio-system-stage" />,
}))

vi.mock('@/components/studio/stages/ContinuationResultsStage', () => ({
  ContinuationResultsStage: () => <div data-testid="continuation-results-stage" />,
}))

vi.mock('@/components/novel-copilot/NovelCopilotDrawer', () => ({
  NovelCopilotDrawer: () => <div data-testid="novel-copilot-drawer" />,
}))

vi.mock('@/hooks/novel/useUpdateChapter', () => ({
  useUpdateChapter: (...args: unknown[]) => mockUseUpdateChapter(...args),
}))

vi.mock('@/hooks/novel/useCreateChapter', () => ({
  useCreateChapter: (...args: unknown[]) => mockUseCreateChapter(...args),
}))

vi.mock('@/hooks/novel/useDeleteChapter', () => ({
  useDeleteChapter: (...args: unknown[]) => mockUseDeleteChapter(...args),
}))

vi.mock('@/hooks/world/useEntities', () => ({
  useWorldEntities: (...args: unknown[]) => mockUseWorldEntities(...args),
}))

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
}))

vi.mock('@/hooks/world/useBootstrap', () => ({
  useBootstrapStatus: (...args: unknown[]) => mockUseBootstrapStatus(...args),
  useTriggerBootstrap: (...args: unknown[]) => mockUseTriggerBootstrap(...args),
}))

vi.mock('@/hooks/useDebouncedAutoSave', () => ({
  useDebouncedAutoSave: (...args: unknown[]) => mockUseDebouncedAutoSave(...args),
}))

vi.mock('@/hooks/novel/useContinuationSetupState', () => ({
  useContinuationSetupState: (...args: unknown[]) => mockUseContinuationSetupState(...args),
}))

vi.mock('@/lib/generationResultsDebugStorage', () => ({
  readGenerationResultsDebug: (...args: unknown[]) => mockReadGenerationResultsDebug(...args),
}))

vi.mock('@/components/atlas/workbench/atlasAssistWorkbenchLoader', () => ({
  loadAtlasAssistWorkbench: (...args: unknown[]) => mockLoadAtlasAssistWorkbench(...args),
  scheduleAtlasAssistWorkbenchPrefetch: (...args: unknown[]) => mockScheduleAtlasAssistWorkbenchPrefetch(...args),
}))

vi.mock('@/services/api', () => ({
  api: {
    getNovel: vi.fn(),
    listChaptersMeta: vi.fn(),
    getChapter: vi.fn(),
    listChapters: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    code?: string
  },
}))

import { api } from '@/services/api'

const mockGetNovel = api.getNovel as ReturnType<typeof vi.fn>
const mockListChaptersMeta = api.listChaptersMeta as ReturnType<typeof vi.fn>
const mockGetChapter = api.getChapter as ReturnType<typeof vi.fn>

function LocationProbe() {
  const location = useLocation()
  return (
    <>
      <div data-testid="location-path">{location.pathname}</div>
      <div data-testid="location-search">{location.search}</div>
    </>
  )
}

function HistoryBackProbe() {
  const navigate = useNavigate()
  return (
    <button type="button" data-testid="history-back" onClick={() => navigate(-1)}>
      back
    </button>
  )
}

function renderWithStudioShell(
  initialEntry: string | { pathname: string; search?: string; state?: unknown },
  routes?: ReactNode,
) {
  const queryClient = createTestQueryClient()
  const renderResult = render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          {routes ?? (
            <Routes>
              <Route element={<NovelShell />}>
                <Route path="/novel/:novelId" element={<NovelStudioPage />} />
              </Route>
            </Routes>
          )}
        </MemoryRouter>
      </UiLocaleProvider>
    </QueryClientProvider>,
  )

  return {
    queryClient,
    ...renderResult,
  }
}

describe('NovelStudioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockScheduleAtlasAssistWorkbenchPrefetch.mockReturnValue(() => {})

    mockUseUpdateChapter.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue(undefined),
    })
    mockUseCreateChapter.mockReturnValue({
      isPending: false,
      mutate: vi.fn(),
    })
    mockUseDeleteChapter.mockReturnValue({
      mutate: vi.fn(),
    })
    mockUseWorldEntities.mockReturnValue({
      data: [{ id: 1, name: '主角' }],
      isLoading: false,
    })
    mockUseWorldSystems.mockReturnValue({
      data: [],
      isLoading: false,
    })
    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })
    mockUseTriggerBootstrap.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    })
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'idle',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow: vi.fn().mockResolvedValue(undefined),
      cancel: vi.fn(),
    })
    mockUseContinuationSetupState.mockReturnValue({
      instruction: '',
      setInstruction: vi.fn(),
      selectedLength: 'medium',
      setSelectedLength: vi.fn(),
      advancedOpen: false,
      setAdvancedOpen: vi.fn(),
      contextChapters: 3,
      setContextChapters: vi.fn(),
      numVersions: 2,
      setNumVersions: vi.fn(),
      temperature: 0.7,
      setTemperature: vi.fn(),
      handleGenerate: vi.fn(),
    })

    mockGetNovel.mockResolvedValue(buildNovelResponse())
    mockListChaptersMeta.mockResolvedValue([
      {
        id: 11,
        novel_id: 7,
        chapter_number: 1,
        title: '开端',
        source_chapter_label: '第一章 开端',
        source_chapter_number: 1,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 13,
        novel_id: 7,
        chapter_number: 3,
        title: '归来',
        source_chapter_label: '第844章 归来',
        source_chapter_number: 844,
        created_at: '2026-03-03T00:00:00Z',
      },
    ])
    mockGetChapter.mockImplementation(async (_novelId: number, chapterNum: number) => ({
      id: chapterNum,
      novel_id: 7,
      chapter_number: chapterNum,
      title: chapterNum === 3 ? '归来' : '开端',
      source_chapter_label: chapterNum === 3 ? '第844章 归来' : '第一章 开端',
      source_chapter_number: chapterNum === 3 ? 844 : 1,
      content: chapterNum === 3 ? '第三章内容' : '第一章内容',
      created_at: '2026-03-03T00:00:00Z',
      updated_at: null,
    }))
    mockReadGenerationResultsDebug.mockReturnValue(null)
  })

  it('uses the requested chapter from the studio URL instead of falling back to chapter one', async () => {
    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    expect(screen.getAllByText('第 3 章').length).toBeGreaterThan(0)
    expect(screen.getByText('归来')).toBeInTheDocument()
    expect(screen.queryByText('第一章内容')).not.toBeInTheDocument()
    expect(mockGetChapter).toHaveBeenCalledWith(7, 3)
  })

  it('shows a preparation gate while the upload ingest pipeline is still running', async () => {
    mockGetNovel.mockResolvedValue({
      id: 7,
      title: '测试小说',
      is_seeded_demo: false,
      created_at: '2026-03-01T00:00:00Z',
      window_index: {
        status: 'missing',
        revision: 0,
        built_revision: null,
        error: null,
        readiness: 'accepting',
        capabilities: {
          chapters_available: false,
          whole_book_index_available: false,
          bootstrap_available: false,
          recent_fallback_only: false,
        },
        ingest: {
          status: 'queued',
          stage: 'accepted',
          size_tier: 'large',
          source_bytes: 1024,
          source_chars: null,
          chapter_count: null,
          requested_language: 'zh',
          resolved_language: null,
          auto_index_plan: null,
          bootstrap_plan: null,
          readiness_mode: null,
          error: null,
        },
        job: null,
      },
    })
    mockUseWorldEntities.mockReturnValue({ data: [], isLoading: false })
    mockUseWorldSystems.mockReturnValue({ data: [], isLoading: false })
    mockListChaptersMeta.mockResolvedValue([])

    renderWithStudioShell('/novel/7')

    expect(await screen.findByTestId('studio-preparation-gate')).toBeInTheDocument()
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()
  })

  it('keeps the studio blocked while initial bootstrap extraction is still running', async () => {
    mockGetNovel.mockResolvedValue({
      id: 7,
      title: '测试小说',
      is_seeded_demo: false,
      created_at: '2026-03-01T00:00:00Z',
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
        ingest: {
          status: 'completed',
          stage: 'completed',
          size_tier: 'large',
          source_bytes: 1024,
          source_chars: 2048,
          chapter_count: 2,
          requested_language: 'zh',
          resolved_language: 'zh',
          auto_index_plan: 'immediate',
          bootstrap_plan: 'immediate',
          readiness_mode: 'ready',
          error: null,
        },
        job: null,
      },
    })
    mockUseWorldEntities.mockReturnValue({ data: [], isLoading: false })
    mockUseWorldSystems.mockReturnValue({ data: [], isLoading: false })
    mockUseBootstrapStatus.mockReturnValue({
      data: {
        id: 9,
        novel_id: 7,
        mode: 'initial',
        status: 'pending',
        progress: { step: 0, detail: 'queued' },
        result: {
          entities_found: 0,
          relationships_found: 0,
          index_refresh_only: false,
        },
        error: null,
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
      },
      isLoading: false,
    })

    renderWithStudioShell('/novel/7')

    expect(await screen.findByTestId('studio-preparation-gate')).toBeInTheDocument()
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()
    expect(screen.queryByText('第一章内容')).not.toBeInTheDocument()
  })

  it('keeps the studio blocked while deferred auto-bootstrap is waiting on whole-book index', async () => {
    mockGetNovel.mockResolvedValue({
      id: 7,
      title: '测试小说',
      is_seeded_demo: false,
      created_at: '2026-03-01T00:00:00Z',
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
          source_chars: 4096,
          chapter_count: 4,
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
    })
    mockUseWorldEntities.mockReturnValue({ data: [], isLoading: false })
    mockUseWorldSystems.mockReturnValue({ data: [], isLoading: false })
    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })

    renderWithStudioShell('/novel/7')

    expect(await screen.findByTestId('studio-preparation-gate')).toBeInTheDocument()
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()
    expect(screen.queryByText('第一章内容')).not.toBeInTheDocument()
  })

  it('waits to load chapter metadata until uploaded chapters are actually available', async () => {
    mockGetNovel
      .mockResolvedValueOnce({
        id: 7,
        title: '测试小说',
        is_seeded_demo: false,
        total_chapters: 0,
        created_at: '2026-03-01T00:00:00Z',
        window_index: {
          status: 'missing',
          revision: 0,
          built_revision: null,
          error: null,
          readiness: 'accepting',
          capabilities: {
            chapters_available: false,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'queued',
            stage: 'accepted',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: null,
            chapter_count: null,
            requested_language: 'zh',
            resolved_language: null,
            auto_index_plan: null,
            bootstrap_plan: 'immediate',
            readiness_mode: null,
            error: null,
          },
          job: null,
        },
      })
      .mockResolvedValueOnce({
        id: 7,
        title: '测试小说',
        is_seeded_demo: false,
        total_chapters: 2,
        created_at: '2026-03-01T00:00:00Z',
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
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: 2048,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'immediate',
            bootstrap_plan: 'immediate',
            readiness_mode: 'full_target',
            error: null,
          },
          job: null,
        },
      })
    mockListChaptersMeta.mockResolvedValue([
      {
        id: 11,
        novel_id: 7,
        chapter_number: 1,
        title: '开端',
        source_chapter_label: '第一章 开端',
        source_chapter_number: 1,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 12,
        novel_id: 7,
        chapter_number: 2,
        title: '归来',
        source_chapter_label: '第二章 归来',
        source_chapter_number: 2,
        created_at: '2026-03-02T00:00:00Z',
      },
    ])

    const { queryClient } = renderWithStudioShell('/novel/7')

    expect(await screen.findByTestId('studio-preparation-gate')).toBeInTheDocument()
    expect(mockListChaptersMeta).not.toHaveBeenCalled()

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: novelKeys.detail(7) })
    })

    await waitFor(() => {
      expect(mockListChaptersMeta).toHaveBeenCalledWith(7)
    })
    await waitFor(() => {
      expect(screen.getByText('第一章内容')).toBeInTheDocument()
    })
  })

  it('opens the chapter workspace instead of empty-world onboarding for upload-entry navigation', async () => {
    mockUseWorldEntities.mockReturnValue({ data: [], isLoading: false })
    mockUseWorldSystems.mockReturnValue({ data: [], isLoading: false })
    const user = userEvent.setup()

    renderWithStudioShell({
      pathname: '/novel/7',
      state: { novwrEntry: 'upload' },
    })

    await waitFor(() => {
      expect(screen.getByText('第一章内容')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()
    expect(screen.getByTestId('studio-rail-chapters')).toBeInTheDocument()

    await user.click(screen.getByTestId('studio-rail-continuation'))

    await waitFor(() => {
      expect(screen.getByTestId('continuation-setup')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()
  })

  it('shows the demo-first onboarding for the seeded demo novel', async () => {
    mockGetNovel.mockResolvedValue(buildNovelResponse({
      title: '西游记',
      is_seeded_demo: true,
      window_index: {
        status: 'fresh',
        revision: 1,
        built_revision: 1,
        error: null,
        job: null,
      },
    }))

    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('demo-first-onboarding')).toBeInTheDocument()
    })
  })

  it('keeps the demo guide visible when the user is mid-way through the sample flow', async () => {
    localStorage.setItem(
      'novwr_demo_first_onboarding_dismissed_7_2026-03-01T00:00:00Z',
      JSON.stringify({
        version: 2,
        status: 'in_progress',
        visited: {
          chapter: true,
          atlas: false,
          write: false,
          copilot: false,
        },
      }),
    )
    mockGetNovel.mockResolvedValue(buildNovelResponse({
      title: '西游记',
      is_seeded_demo: true,
      window_index: {
        status: 'fresh',
        revision: 1,
        built_revision: 1,
        error: null,
        job: null,
      },
    }))

    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('demo-first-onboarding')).toBeInTheDocument()
    })
  })

  it('replaces the prominent demo guide with a reopen control after completion', async () => {
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
    mockGetNovel.mockResolvedValue(buildNovelResponse({
      title: '西游记',
      is_seeded_demo: true,
      window_index: {
        status: 'fresh',
        revision: 1,
        built_revision: 1,
        error: null,
        job: null,
      },
    }))

    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('demo-first-onboarding')).not.toBeInTheDocument()
    expect(screen.getByTestId('demo-first-onboarding-reopen')).toBeInTheDocument()
  })

  it('can reopen the demo guide from the studio URL even after completion', async () => {
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
    mockGetNovel.mockResolvedValue(buildNovelResponse({
      title: '西游记',
      is_seeded_demo: true,
      window_index: {
        status: 'fresh',
        revision: 1,
        built_revision: 1,
        error: null,
        job: null,
      },
    }))

    renderWithStudioShell('/novel/7?chapter=3&demoGuide=open')

    await waitFor(() => {
      expect(screen.getByTestId('demo-first-onboarding')).toBeInTheDocument()
    })
  })

  it('does not show demo-first onboarding for a normal novel that shares the old demo title', async () => {
    mockGetNovel.mockResolvedValue(buildNovelResponse({
      title: '西游记',
      is_seeded_demo: false,
      window_index: {
        status: 'fresh',
        revision: 1,
        built_revision: 1,
        error: null,
        job: null,
      },
    }))

    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('demo-first-onboarding')).not.toBeInTheDocument()
  })

  it('renders the in-shell entity inspection stage when the studio route requests an entity target', async () => {
    renderWithStudioShell('/novel/7?stage=entity&entity=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-entity-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell review stage when the studio route requests review mode', async () => {
    renderWithStudioShell('/novel/7?stage=review&reviewKind=relationships&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-review-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell relationship stage when the studio route requests relationship mode', async () => {
    renderWithStudioShell('/novel/7?stage=relationship&entity=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-relationship-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell system stage when the studio route requests system mode', async () => {
    renderWithStudioShell('/novel/7?stage=system&system=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-system-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell results stage from the studio host route', async () => {
    renderWithStudioShell('/novel/7?stage=results&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('continuation-results-stage')).toBeInTheDocument()
    })
  })

  it('searches chapters by exact internal chapter numbers and titles', async () => {
    mockListChaptersMeta.mockResolvedValue([
      {
        id: 17,
        novel_id: 7,
        chapter_number: 17,
        title: '正主',
        source_chapter_label: '第十七章 正主',
        source_chapter_number: 17,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 417,
        novel_id: 7,
        chapter_number: 417,
        title: '可真够懒的',
        source_chapter_label: null,
        source_chapter_number: null,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 420,
        novel_id: 7,
        chapter_number: 420,
        title: '放一块',
        source_chapter_label: '第420章 放一块',
        source_chapter_number: 420,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 84,
        novel_id: 7,
        chapter_number: 84,
        title: '无奈之举',
        source_chapter_label: '第八十四章 无奈之举',
        source_chapter_number: 84,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 844,
        novel_id: 7,
        chapter_number: 544,
        title: '还是搬而泣之的好',
        source_chapter_label: '第844章 还是搬而泣之的好',
        source_chapter_number: 844,
        created_at: '2026-03-02T00:00:00Z',
      },
    ])
    mockGetChapter.mockImplementation(async (_novelId: number, chapterNum: number) => ({
      id: chapterNum,
      novel_id: 7,
      chapter_number: chapterNum,
      title: {
        17: '正主',
        84: '第八十四章 无奈之举',
        417: '可真够懒的',
        420: '放一块',
        544: '还是搬而泣之的好',
      }[chapterNum] ?? '未知章节',
      source_chapter_label: {
        17: '第十七章 正主',
        84: '第八十四章 无奈之举',
        420: '第420章 放一块',
        544: '第844章 还是搬而泣之的好',
      }[chapterNum] ?? null,
      source_chapter_number: {
        17: 17,
        84: 84,
        420: 420,
        544: 844,
      }[chapterNum] ?? null,
      content: `第${chapterNum}章内容`,
      created_at: '2026-03-03T00:00:00Z',
      updated_at: null,
    }))

    const user = userEvent.setup()
    renderWithStudioShell('/novel/7?chapter=84')

    await waitFor(() => {
      expect(screen.getByText('第84章内容')).toBeInTheDocument()
    })

    const searchInput = screen.getByTestId('studio-rail-search')
    const chapterRail = within(screen.getByTestId('studio-rail-chapters'))

    await user.type(searchInput, '17')

    expect(chapterRail.getByRole('button', { name: '第 17 章 · 正主' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 417 章 · 可真够懒的' })).not.toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 420 章 · 放一块' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '544')

    expect(chapterRail.getByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 84 章 · 无奈之举' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '84')

    expect(chapterRail.getByRole('button', { name: '第 84 章 · 无奈之举' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '无奈')

    expect(chapterRail.getByRole('button', { name: '第 84 章 · 无奈之举' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).not.toBeInTheDocument()
  })

  it('keeps the injection summary rail visible during results-derived studio inspection', async () => {
    mockReadGenerationResultsDebug.mockReturnValue({
      context_chapters: 3,
      injected_entities: ['主角'],
      injected_relationships: [],
      injected_systems: [],
      relevant_entity_ids: [1],
      ambiguous_keywords_disabled: [],
      drift_warnings: [],
      prose_warnings: [],
    })

    renderWithStudioShell('/novel/7?stage=entity&entity=1&chapter=3&resultsChapter=3&resultsContinuations=0:101&resultsTotalVariants=1&artifactPanel=injection_summary&summaryCategory=entities')

    await waitFor(() => {
      expect(screen.getByTestId('studio-entity-stage')).toBeInTheDocument()
    })

    expect(screen.getByTestId('injection-summary-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('studio-research-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('studio-world-entry-panel')).not.toBeInTheDocument()
  })

  it('waits for chapter save success before navigating from studio to atlas', async () => {
    let resolveSave: (() => void) | null = null
    const saveNow = vi.fn().mockImplementation(() => new Promise<void>((resolve) => {
      resolveSave = resolve
    }))
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'unsaved',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow,
      cancel: vi.fn(),
    })

    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '编辑' }))
    expect(screen.getByTestId('chapter-editor')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: /Atlas 世界模型/ })[0])

    expect(saveNow).toHaveBeenCalledWith('第三章内容')
    expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')

    resolveSave?.()

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/world/7')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('originStage=chapter')
    expect(screen.getByTestId('location-search')).toHaveTextContent('originChapter=3')
  })

  it('best-effort prefetches Atlas assist on mount and warms it again on atlas-cta hover', async () => {
    const user = userEvent.setup()

    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    expect(mockScheduleAtlasAssistWorkbenchPrefetch).toHaveBeenCalled()
    expect(mockLoadAtlasAssistWorkbench).not.toHaveBeenCalled()

    await user.hover(screen.getAllByRole('button', { name: /Atlas 世界模型/ })[0]!)

    expect(mockLoadAtlasAssistWorkbench).toHaveBeenCalledTimes(1)
  })

  it('stays in studio when chapter save fails before atlas navigation', async () => {
    const saveNow = vi.fn().mockRejectedValue(new Error('save failed'))
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'unsaved',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow,
      cancel: vi.fn(),
    })

    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '编辑' }))
    await user.click(screen.getAllByRole('button', { name: /Atlas 世界模型/ })[0])

    await waitFor(() => {
      expect(saveNow).toHaveBeenCalledWith('第三章内容')
    })
    expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')
    expect(screen.getByTestId('chapter-editor')).toBeInTheDocument()
  })

  it('keeps studio world-generation as an explicit handoff before opening Atlas review', async () => {
    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('world-build-generate'))
    await user.click(screen.getByTestId('mock-world-gen-success'))

    expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=generate_review')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryEntities=1')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntrySystems=1')

    await user.click(screen.getByTestId('studio-world-entry-handoff-action'))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/world/7')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('tab=review')
    expect(screen.getByTestId('location-search')).toHaveTextContent('kind=entities')
    expect(screen.getByTestId('location-search')).toHaveTextContent('originStage=chapter')
    expect(screen.getByTestId('location-search')).toHaveTextContent('originChapter=3')

    await user.click(screen.getByTestId('history-back'))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=generate_review')
    expect(screen.getByTestId('studio-world-entry-handoff-action')).toBeInTheDocument()
  })

  it('preserves a pending extraction marker when Studio hands off to Atlas before async completion', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(ACTIVE_PENDING_NOW_MS)
    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                </>
              )}
            />
            <Route
              path="/world/:novelId"
              element={<LocationProbe />}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('mock-bootstrap-start'))

    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryPending=extract')
    expect(screen.getByTestId('location-search')).toHaveTextContent(`worldEntryPendingAt=${ACTIVE_PENDING_STARTED_AT}`)
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryPendingJob=')

    await user.click(screen.getAllByRole('button', { name: /Atlas 世界模型/ })[0]!)

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/world/7')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryPending=extract')
    expect(screen.getByTestId('location-search')).toHaveTextContent(`worldEntryPendingAt=${ACTIVE_PENDING_STARTED_AT}`)
    dateNowSpy.mockRestore()
  })

  it('re-elevates the world-entry rail section when a pending extraction marker is restored from the URL', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(ACTIVE_PENDING_NOW_MS)
    renderWithStudioShell(`/novel/7?chapter=3&worldEntryPending=extract&worldEntryPendingAt=${ACTIVE_PENDING_STARTED_AT}`)

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    const sections = screen.getByTestId('studio-support-rail-sections')
    const panels = Array.from(sections.querySelectorAll('[data-testid="studio-world-entry-panel"], [data-testid="studio-research-panel"]'))
      .map((node) => node.getAttribute('data-testid'))

    expect(screen.getByTestId('studio-assistant-rail')).toHaveAttribute('data-world-entry-stage', 'attention')
    expect(screen.getByTestId('studio-world-entry-panel')).toHaveAttribute('data-prominence', 'elevated')
    expect(screen.getByTestId('studio-world-entry-attention-banner')).toHaveAttribute('data-tone', 'running')
    expect(panels).toEqual(['studio-world-entry-panel', 'studio-research-panel'])
    dateNowSpy.mockRestore()
  })

  it('upgrades a pending extraction marker into a terminal handoff when Studio remounts after completion', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(ACTIVE_PENDING_NOW_MS)
    mockUseBootstrapStatus.mockReturnValue({
      data: {
        job_id: 41,
        novel_id: 7,
        mode: 'initial',
        initialized: true,
        status: 'completed',
        progress: { step: 5, detail: '完成' },
        result: {
          entities_found: 2,
          relationships_found: 1,
          index_refresh_only: false,
        },
        error: null,
        created_at: '2026-03-30T00:00:00Z',
        updated_at: '2026-03-30T00:01:00Z',
      },
      isLoading: false,
    })

    renderWithStudioShell(
      `/novel/7?chapter=3&worldEntryPending=extract&worldEntryPendingAt=${ACTIVE_PENDING_STARTED_AT}`,
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=extract_review')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryEntities=2')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryRelationships=1')
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryPending=')
    dateNowSpy.mockRestore()
  })

  it('clears expired pending extraction markers after reload so Studio does not stay stuck in running attention forever', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-03-31T01:00:00Z'))

    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })

    renderWithStudioShell(
      '/novel/7?chapter=3&worldEntryPending=extract&worldEntryPendingAt=1743375600000',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryPending=')
    })

    dateNowSpy.mockRestore()
  })

  it('renders the studio rail in English when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    renderWithStudioShell('/novel/7?chapter=3')

    expect(await screen.findByPlaceholderText('Search chapters...')).toBeInTheDocument()
    expect(screen.getByText('Workspace')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Atlas world model/i }).length).toBeGreaterThan(0)
    expect(screen.getByText('Chapters')).toBeInTheDocument()
  })
})
