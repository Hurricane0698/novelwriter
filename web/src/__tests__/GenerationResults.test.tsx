import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ContinuationResultsStage } from '@/components/studio/stages/ContinuationResultsStage'
import { TextSourceLink } from '@/components/novel-copilot/TextSourceLink'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { createNovelWrapper } from '@/__tests__/support/novel'
import { adoptedChapter, continuation, deferred } from '@/__tests__/support/continuation'
import { MARKDOWN_CHAPTER_BODY_INVALID } from '@/lib/chapterMutationError'
import { ApiError } from '@/services/apiClient'
import type { Chapter, Continuation } from '@/types/api'

vi.mock('@/components/ui/plain-text-content', () => ({
  PlainTextContent: ({
    content,
    emptyLabel,
  }: {
    content?: string | null
    emptyLabel?: string
  }) => <div data-testid="plain-text-content">{content || emptyLabel}</div>,
}))

vi.mock('@/components/generation/DriftWarningPopover', () => ({
  DriftWarningPopover: () => null,
}))

vi.mock('@/services/api', () => ({
  api: {
    getContinuations: vi.fn(),
    updateContinuation: vi.fn(),
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

function setCandidates(rows: Array<Partial<Continuation> & Pick<Continuation, 'id' | 'content'>>) {
  const candidates = rows.map((row) => ({ ...continuation(row.id, row.content), ...row }))
  mockGetContinuations.mockImplementation(async (_novelId: number, ids: number[]) => (
    ids.map((id) => candidates.find((candidate) => candidate.id === id)!)
  ))
  vi.mocked(api.updateContinuation).mockImplementation(async (_novelId, id, content) => {
    const row = candidates.find((candidate) => candidate.id === id)!
    Object.assign(row, { edited_content: content, content_hash: continuation(id, content).content_hash })
    return { ...row }
  })
}

const singleResult = '/novel/7?stage=results&chapter=3&continuations=0:101&total_variants=1'
const twoResults = '/novel/7?stage=results&chapter=3&continuations=0:101,1:102&total_variants=2'

function ResultsStage({ contentFormat = 'plain_text', isActive = true }: {
  contentFormat?: 'plain_text' | 'markdown'; isActive?: boolean
}) {
  return <ContinuationResultsStage novelId={7} contentFormat={contentFormat} isActive={isActive}
    activeChapterNum={3} showInjectionSummaryRail={false}
    onToggleInjectionSummaryRail={vi.fn()} onDebugChange={vi.fn()} />
}

function ResultsRoute({ contentFormat, sourceSwitch, citation }: {
  contentFormat: 'plain_text' | 'markdown'; sourceSwitch: boolean; citation: boolean
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const { getTextTarget } = useNovelCopilot()
  const inResults = new URLSearchParams(location.search).get('stage') === 'results'
  return <>
    {inResults ? <>
      <ResultsStage contentFormat={contentFormat} />
      {sourceSwitch && <ResultsSourceSwitchProbe />}
      {citation && <TextSourceLink novelId={7} source={{ chapter_number: 1 }}
        beforeNavigate={async () => { await getTextTarget({ kind: 'continuation', id: 102 })!.prepare() }} />}
    </> : <button onClick={() => navigate(-1)}>Return to results</button>}
    <LocationProbe />
  </>
}

function renderResults({ entry = singleResult, contentFormat = 'plain_text', sourceSwitch = false, session = false, citation = false } : {
  entry?: NonNullable<ComponentProps<typeof MemoryRouter>['initialEntries']>[number]
  contentFormat?: 'plain_text' | 'markdown'
  sourceSwitch?: boolean
  session?: boolean
  citation?: boolean
} = {}) {
  return render(<MemoryRouter initialEntries={[entry]}>
    <Routes><Route path="/novel/:novelId" element={session ? <ResultsSessionProbe /> :
      <ResultsRoute contentFormat={contentFormat} sourceSwitch={sourceSwitch} citation={citation} />
    } /></Routes>
  </MemoryRouter>, { wrapper: createNovelWrapper() })
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
      <ResultsStage isActive={isActive} />
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
    localStorage.clear()
    vi.stubGlobal('crypto', webcrypto)

    setCandidates([continuation(101, '已持久化的续写结果')])
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
    mockCreateChapter.mockResolvedValue(adoptedChapter('续写结果'))
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each(['citation', 'regenerate'] as const)('preserves edited candidates across %s navigation and adopts the edited text', async (navigation) => {
    setCandidates([continuation(101, '候选一'), continuation(102, '候选二')])
    renderResults({ entry: twoResults, citation: true })
    await userEvent.click(await screen.findByRole('button', { name: '编辑修改稿' }))
    await userEvent.clear(screen.getByTestId('candidate-draft-editor'))
    await userEvent.type(screen.getByTestId('candidate-draft-editor'), '作者修改候选一')
    await userEvent.click(screen.getByRole('button', { name: '版本 2' }))

    if (navigation === 'citation') await userEvent.click(screen.getByRole('link', { name: '查看原文 · 1' }))
    else await userEvent.click(screen.getByRole('button', { name: '重新生成' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Return to results' }))
    await waitFor(() => expect(screen.getByTestId('plain-text-content')).toHaveTextContent('作者修改候选一'))
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await waitFor(() => expect(mockCreateChapter).toHaveBeenCalledWith(7, { content: '作者修改候选一' }))
    expect(api.updateContinuation).toHaveBeenCalledTimes(1)
    expect(api.updateContinuation).toHaveBeenCalledWith(7, 101, '作者修改候选一', continuation(101, '候选一').content_hash)
  })

  it('recovers persisted results inside the embedded studio results stage without hook-order crashes', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    renderResults()

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

    renderResults({ entry: {
      pathname: '/novel/7', search: '?stage=results&chapter=3',
      state: { novelId: 7, streamParams: { num_versions: 1 } },
    } })

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
        continuationRequestId: 'test-continuation-request-id',
      },
    )
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('continuations=0%3A201')
      expect(screen.getByTestId('location-search')).toHaveTextContent('total_variants=1')
    })
  })

  it('renders persisted Markdown candidates exactly as they will appear after adoption', async () => {
    setCandidates([continuation(101, '**加粗候选**\n\n### 小节')])

    renderResults({ contentFormat: 'markdown' })

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
    setCandidates([continuation(101, '```markdown\n未闭合候选'), continuation(102, '边界安全的候选')])

    renderResults({ entry: twoResults, contentFormat: 'markdown' })

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
    const staleAdoption = deferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => staleAdoption.promise)
    mockGetContinuations.mockImplementation(async (_novelId: number, ids: number[]) => (
      ids.map((id) => ({
        id,
        novel_id: 7,
        content: '相同正文',
        created_at: '2026-03-03T00:00:00Z',
      }))
    ))

    renderResults({ sourceSwitch: true })

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
    const committedAdoption = deferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)
    setCandidates([continuation(101, '候选一'), continuation(102, '候选二')])

    renderResults({ entry: twoResults })

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByRole('button', { name: '版本 2' }))
    await act(async () => {
      committedAdoption.resolve(adoptedChapter('候选一'))
      await committedAdoption.promise
    })

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=4')
    })
  })

  it('confirms committed adoption after a same-source UI-only replace navigation', async () => {
    const committedAdoption = deferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)

    renderResults({ session: true })

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByTestId('replace-results-ui-state'))
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('artifactPanel=injection_summary')
    })

    await act(async () => {
      committedAdoption.resolve(adoptedChapter('已提交候选'))
      await committedAdoption.promise
    })

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=4')
    })
  })

  it('does not navigate for a committed adoption after the results stage becomes inactive', async () => {
    const committedAdoption = deferred<Chapter>()
    mockCreateChapter.mockImplementationOnce(() => committedAdoption.promise)

    renderResults({ session: true })

    await waitFor(() => expect(screen.getByTestId('results-adopt-button')).toBeEnabled())
    await userEvent.click(screen.getByTestId('results-adopt-button'))
    await userEvent.click(screen.getByTestId('leave-results-source'))
    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('stage=write')
    })

    await act(async () => {
      committedAdoption.resolve(adoptedChapter('已提交候选'))
      await committedAdoption.promise
    })

    expect(screen.getByTestId('location-search')).toHaveTextContent('stage=write')
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('chapter=4')
  })

  it('shows safe copy when the adopt request fails', async () => {
    mockCreateChapter.mockRejectedValue(new Error('raw backend diagnostic'))

    renderResults()

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
