import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { ContinuationResultsStage } from '@/components/studio/stages/ContinuationResultsStage'
import { createTestQueryClient } from '@/__tests__/support/queryClient'
import { MARKDOWN_CHAPTER_BODY_INVALID } from '@/lib/chapterMutationError'
import { ApiError } from '@/services/apiClient'
import type { Chapter } from '@/types/api'

const mockUseAuth = vi.fn()

vi.mock('@/components/ui/plain-text-content', () => ({
  PlainTextContent: ({
    content,
    emptyLabel,
  }: {
    content?: string | null
    emptyLabel?: string
  }) => <div data-testid="plain-text-content">{content || emptyLabel}</div>,
}))

vi.mock('@/components/feedback/FeedbackForm', () => ({
  FeedbackForm: () => null,
}))

vi.mock('@/components/generation/DriftWarningPopover', () => ({
  DriftWarningPopover: () => null,
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: (...args: unknown[]) => mockUseAuth(...args),
}))

vi.mock('@/services/api', () => ({
  api: {
    getContinuations: vi.fn(),
    continueNovel: vi.fn(),
    createChapter: vi.fn(),
    submitFeedback: vi.fn(),
  },
  streamContinuation: vi.fn(),
  buildContinuationRequestId: vi.fn(() => 'test-continuation-request-id'),
  ApiError: class ApiError extends Error {
    status: number

    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

import { api, streamContinuation } from '@/services/api'

const mockGetContinuations = api.getContinuations as ReturnType<typeof vi.fn>
const mockContinueNovel = api.continueNovel as ReturnType<typeof vi.fn>
const mockCreateChapter = api.createChapter as ReturnType<typeof vi.fn>
const mockStreamContinuation = streamContinuation as ReturnType<typeof vi.fn>

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function ResultsSourceSwitchProbe() {
  const navigate = useNavigate()
  return (
    <>
      <button
        type="button"
        data-testid="switch-results-b"
        onClick={() => navigate('/novel/7?stage=results&chapter=3&continuations=0:102&total_variants=1')}
      >
        switch B
      </button>
      <button
        type="button"
        data-testid="switch-results-a"
        onClick={() => navigate('/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1')}
      >
        switch A
      </button>
    </>
  )
}

function ResultsSessionProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  const searchParams = new URLSearchParams(location.search)
  const isActive = searchParams.get('stage') === 'results'

  return (
    <>
      <ContinuationResultsStage
        novelId={7}
        contentFormat="plain_text"
        isActive={isActive}
        activeChapterNum={3}
        showInjectionSummaryRail={false}
        onToggleInjectionSummaryRail={vi.fn()}
        onDebugChange={vi.fn()}
      />
      <button
        type="button"
        data-testid="replace-results-ui-state"
        onClick={() => {
          const next = new URLSearchParams(location.search)
          next.set('artifactPanel', 'injection_summary')
          navigate(
            { pathname: location.pathname, search: next.toString() },
            { replace: true, state: location.state },
          )
        }}
      >
        replace results UI state
      </button>
      <button
        type="button"
        data-testid="leave-results-source"
        onClick={() => {
          const next = new URLSearchParams(location.search)
          next.set('stage', 'write')
          navigate(
            { pathname: location.pathname, search: next.toString() },
            { state: location.state },
          )
        }}
      >
        leave results
      </button>
      <LocationProbe />
    </>
  )
}

describe('ContinuationResultsStage runtime', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()

    mockUseAuth.mockReturnValue({
      user: { feedback_submitted: false },
      refreshQuota: vi.fn().mockResolvedValue(undefined),
    })

    mockGetContinuations.mockResolvedValue([
      {
        id: 101,
        novel_id: 7,
        content: '已持久化的续写结果',
        created_at: '2026-03-03T00:00:00Z',
      },
    ])
    mockContinueNovel.mockResolvedValue({
      continuations: [],
      debug: {
        context_chapters: 3,
        injected_systems: [],
        injected_entities: [],
        injected_relationships: [],
        injected_context_summaries: [],
        relevant_entity_ids: [],
        ambiguous_keywords_disabled: [],
        drift_warnings: [],
        prose_warnings: [],
      },
    })
    mockCreateChapter.mockResolvedValue({
      id: 301,
      novel_id: 7,
      chapter_number: 4,
      title: '',
      source_chapter_label: null,
      source_chapter_number: null,
      source_volume_title: null,
      content: '续写结果',
      created_at: '2026-03-03T00:00:00Z',
      updated_at: null,
    })
  })

  it('recovers persisted results inside the embedded studio results stage without hook-order crashes', async () => {
    const queryClient = createTestQueryClient()
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <ContinuationResultsStage
                    novelId={7}
                    contentFormat="plain_text"
                    isActive
                    activeChapterNum={3}
                    showInjectionSummaryRail={false}
                    onToggleInjectionSummaryRail={vi.fn()}
                    onDebugChange={vi.fn()}
                  />
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    expect(screen.getByText('正在加载续写结果...')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByTestId('plain-text-content')).toHaveTextContent('已持久化的续写结果')
    })

    expect(mockGetContinuations).toHaveBeenCalledWith(7, [101])
    expect(
      consoleErrorSpy.mock.calls.some((call) => call.some((arg) => String(arg).includes('Rendered more hooks than during the previous render'))),
    ).toBe(false)

    consoleErrorSpy.mockRestore()
  })

  it('falls back to non-stream continuation when early streaming transport fails', async () => {
    const queryClient = createTestQueryClient()

    mockStreamContinuation.mockReturnValue({
      [Symbol.asyncIterator]() {
        return {
          async next() {
            throw new Error('Malformed NDJSON line: {bad-json}')
          },
        }
      },
    })
    mockContinueNovel.mockResolvedValue({
      continuations: [
        {
          id: 201,
          novel_id: 7,
          chapter_number: 4,
          content: '这是稳定返回的续写结果',
          rating: null,
          created_at: '2026-03-21T00:00:00Z',
        },
      ],
      debug: {
        context_chapters: 3,
        injected_systems: [],
        injected_entities: [],
        injected_relationships: [],
        injected_context_summaries: [],
        relevant_entity_ids: [],
        ambiguous_keywords_disabled: [],
        drift_warnings: [],
        prose_warnings: [],
      },
    })

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/novel/7',
                search: '?stage=results&chapter=3',
                state: {
                  novelId: 7,
                  streamParams: { num_versions: 1 },
                },
              },
            ]}
          >
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <>
                    <ContinuationResultsStage
                      novelId={7}
                      contentFormat="plain_text"
                      isActive
                      activeChapterNum={3}
                      showInjectionSummaryRail={false}
                      onToggleInjectionSummaryRail={vi.fn()}
                      onDebugChange={vi.fn()}
                    />
                    <LocationProbe />
                  </>
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('plain-text-content')).toHaveTextContent('这是稳定返回的续写结果')
    })

    expect(screen.getByText('当前网络不适合实时流式输出，已自动切换到稳定返回模式。')).toBeVisible()
    expect(mockStreamContinuation).toHaveBeenCalledWith(
      7,
      { num_versions: 1 },
      expect.objectContaining({ continuationRequestId: 'test-continuation-request-id' }),
    )
    expect(mockContinueNovel).toHaveBeenCalledWith(
      7,
      { num_versions: 1 },
      {
        deliveryMode: 'stream-fallback',
        continuationRequestId: 'test-continuation-request-id',
      },
    )
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('continuations=0%3A201')
      expect(screen.getByTestId('location-search')).toHaveTextContent('total_variants=1')
    })
  })

  it('renders persisted Markdown candidates exactly as they will appear after adoption', async () => {
    mockGetContinuations.mockResolvedValue([
      {
        id: 101,
        novel_id: 7,
        content: '**加粗候选**\n\n### 小节',
        created_at: '2026-03-03T00:00:00Z',
      },
    ])

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <ContinuationResultsStage
                    novelId={7}
                    contentFormat="markdown"
                    isActive
                    activeChapterNum={3}
                    showInjectionSummaryRail={false}
                    onToggleInjectionSummaryRail={vi.fn()}
                    onDebugChange={vi.fn()}
                  />
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('markdown-content')).toHaveTextContent('加粗候选')
    })
    expect(screen.getByText('加粗候选').tagName).toBe('STRONG')
    expect(screen.queryByTestId('plain-text-content')).not.toBeInTheDocument()
  })

  it('shows a structured validation result when adoption would consume the next Markdown boundary', async () => {
    mockCreateChapter.mockRejectedValueOnce(new ApiError(422, 'raw backend diagnostic', {
      code: MARKDOWN_CHAPTER_BODY_INVALID,
      detail: { code: MARKDOWN_CHAPTER_BODY_INVALID },
    }))
    mockGetContinuations.mockResolvedValue([
      {
        id: 101,
        novel_id: 7,
        content: '```markdown\n未闭合候选',
        created_at: '2026-03-03T00:00:00Z',
      },
      {
        id: 102,
        novel_id: 7,
        content: '边界安全的候选',
        created_at: '2026-03-03T00:00:00Z',
      },
    ])

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101,1:102&total_variants=2']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <ContinuationResultsStage
                    novelId={7}
                    contentFormat="markdown"
                    isActive
                    activeChapterNum={3}
                    showInjectionSummaryRail={false}
                    onToggleInjectionSummaryRail={vi.fn()}
                    onDebugChange={vi.fn()}
                  />
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('results-adopt-button')).toBeEnabled()
    })
    await userEvent.click(screen.getByTestId('results-adopt-button'))

    await waitFor(() => {
      expect(screen.getByTestId('continuation-adopt-error')).toHaveTextContent(
        'Markdown 结构不合法或超过支持的复杂度',
      )
    })
    expect(mockCreateChapter).toHaveBeenCalledWith(7, { content: '```markdown\n未闭合候选' })

    await userEvent.click(screen.getByRole('button', { name: '版本 2' }))
    expect(screen.queryByTestId('continuation-adopt-error')).not.toBeInTheDocument()
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('边界安全的候选')
  })

  it('does not restore an old adopt error after an A to B to A result-source round trip', async () => {
    const staleAdoption = createDeferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => staleAdoption.promise)
    mockGetContinuations.mockImplementation(async (_novelId: number, ids: number[]) => (
      ids.map((id) => ({
        id,
        novel_id: 7,
        content: '相同正文',
        created_at: '2026-03-03T00:00:00Z',
      }))
    ))

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <>
                    <ContinuationResultsStage
                      novelId={7}
                      contentFormat="plain_text"
                      isActive
                      activeChapterNum={3}
                      showInjectionSummaryRail={false}
                      onToggleInjectionSummaryRail={vi.fn()}
                      onDebugChange={vi.fn()}
                    />
                    <ResultsSourceSwitchProbe />
                  </>
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByTestId('switch-results-b'))
    await waitFor(() => expect(mockGetContinuations).toHaveBeenCalledWith(7, [102]))
    await userEvent.click(screen.getByTestId('switch-results-a'))
    await waitFor(() => expect(screen.getByTestId('plain-text-content')).toHaveTextContent('相同正文'))

    await act(async () => {
      staleAdoption.reject(new Error('stale adopt diagnostic'))
      await staleAdoption.promise.catch(() => undefined)
    })
    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    expect(screen.queryByTestId('continuation-adopt-error')).not.toBeInTheDocument()
    expect(screen.queryByText('stale adopt diagnostic')).not.toBeInTheDocument()
  })

  it('confirms an already committed adoption after switching tabs in the same result source', async () => {
    const committedAdoption = createDeferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)
    mockGetContinuations.mockResolvedValue([
      {
        id: 101,
        novel_id: 7,
        content: '候选一',
        created_at: '2026-03-03T00:00:00Z',
      },
      {
        id: 102,
        novel_id: 7,
        content: '候选二',
        created_at: '2026-03-03T00:00:00Z',
      },
    ])

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101,1:102&total_variants=2']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <>
                    <ContinuationResultsStage
                      novelId={7}
                      contentFormat="plain_text"
                      isActive
                      activeChapterNum={3}
                      showInjectionSummaryRail={false}
                      onToggleInjectionSummaryRail={vi.fn()}
                      onDebugChange={vi.fn()}
                    />
                    <LocationProbe />
                  </>
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByRole('button', { name: '版本 2' }))
    await act(async () => {
      committedAdoption.resolve({
        id: 301,
        novel_id: 7,
        chapter_number: 4,
        title: '',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        content: '候选一',
        created_at: '2026-03-03T00:00:00Z',
        updated_at: null,
      })
      await committedAdoption.promise
    })

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=4')
    })
  })

  it('confirms committed adoption after a same-source UI-only replace navigation', async () => {
    const committedAdoption = createDeferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route path="/novel/:novelId" element={<ResultsSessionProbe />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByTestId('replace-results-ui-state'))
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('artifactPanel=injection_summary')
    })

    await act(async () => {
      committedAdoption.resolve({
        id: 301,
        novel_id: 7,
        chapter_number: 4,
        title: '',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        content: '已提交候选',
        created_at: '2026-03-03T00:00:00Z',
        updated_at: null,
      })
      await committedAdoption.promise
    })

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=4')
    })
  })

  it('does not navigate for a committed adoption after the results stage becomes inactive', async () => {
    const committedAdoption = createDeferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route path="/novel/:novelId" element={<ResultsSessionProbe />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByTestId('leave-results-source'))
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('stage=write')
    })

    await act(async () => {
      committedAdoption.resolve({
        id: 301,
        novel_id: 7,
        chapter_number: 4,
        title: '',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        content: '已提交候选',
        created_at: '2026-03-03T00:00:00Z',
        updated_at: null,
      })
      await committedAdoption.promise
    })

    expect(screen.getByTestId('location-search')).toHaveTextContent('stage=write')
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('chapter=4')
  })

  it('shows safe copy when the adopt request fails', async () => {
    mockCreateChapter.mockRejectedValue(new Error('raw backend diagnostic'))

    render(
      <UiLocaleProvider>
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1']}>
            <Routes>
              <Route
                path="/novel/:novelId"
                element={(
                  <ContinuationResultsStage
                    novelId={7}
                    contentFormat="plain_text"
                    isActive
                    activeChapterNum={3}
                    showInjectionSummaryRail={false}
                    onToggleInjectionSummaryRail={vi.fn()}
                    onDebugChange={vi.fn()}
                  />
                )}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('results-adopt-button')).toBeEnabled()
    })
    await userEvent.click(screen.getByTestId('results-adopt-button'))

    await waitFor(() => {
      expect(screen.getByTestId('continuation-adopt-error')).toHaveTextContent('采纳失败，请重试。')
    })
    expect(screen.queryByText('raw backend diagnostic')).not.toBeInTheDocument()
  })
})
