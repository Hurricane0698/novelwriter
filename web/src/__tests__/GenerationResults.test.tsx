import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { GenerationResults } from '@/pages/GenerationResults'
import { ContinuationResultsStage } from '@/components/studio/stages/ContinuationResultsStage'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { createTestQueryClient } from './helpers'

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
    createChapter: vi.fn(),
    submitFeedback: vi.fn(),
  },
  streamContinuation: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number

    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

import { api } from '@/services/api'

const mockGetContinuations = api.getContinuations as ReturnType<typeof vi.fn>

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

describe('GenerationResults compatibility', () => {
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
  })

  it('redirects the legacy results route into the studio-host results stage', async () => {
    render(
      <UiLocaleProvider>
        <MemoryRouter initialEntries={['/novel/7/chapter/3/results?continuations=0:101&total_variants=1']}>
          <Routes>
            <Route path="/novel/:novelId/chapter/:chapterNum/results" element={<GenerationResults />} />
            <Route path="/novel/:novelId" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('stage=results')
    })

    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')
    expect(screen.getByTestId('location-search')).toHaveTextContent('continuations=0%3A101')
    expect(screen.getByTestId('location-search')).toHaveTextContent('total_variants=1')
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
})
