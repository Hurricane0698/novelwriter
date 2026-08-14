import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockNavigate = vi.fn()
const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mockRegenerate = vi.fn()
const mockDelete = vi.fn()
const summaryRows = [{
  id: 9,
  novel_id: 7,
  start_chapter: 1,
  end_chapter: 10,
  title: '第1—10章远期剧情回顾',
  content: '摘要',
  model: 'test-model',
  review_status: 'confirmed' as const,
  is_stale: false,
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}]

vi.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }))
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/contexts/UiLocaleContext', () => ({
  useUiLocale: () => ({ locale: 'zh', t: (key: string) => key }),
}))
vi.mock('@/services/api', () => ({
  api: { updatePreferences: vi.fn().mockResolvedValue(undefined) },
  ApiError: class ApiError extends Error {},
}))
vi.mock('@/hooks/novel/useNovelContextSummaries', () => ({
  useNovelContextSummaries: () => ({
    data: summaryRows,
    isLoading: false,
    isSuccess: true,
    isError: false,
  }),
  useCreateNovelContextSummary: () => ({ mutateAsync: mockCreate, isPending: false }),
  useUpdateNovelContextSummary: () => ({ mutateAsync: mockUpdate, isPending: false }),
  useRegenerateNovelContextSummary: () => ({ mutateAsync: mockRegenerate, isPending: false }),
  useDeleteNovelContextSummary: () => ({
    mutateAsync: mockDelete,
    isPending: false,
    variables: undefined,
  }),
}))

import { useContinuationSetupState } from '@/hooks/novel/useContinuationSetupState'

describe('useContinuationSetupState context summary integration', () => {
  beforeEach(() => vi.clearAllMocks())

  it('passes only selected confirmed summary ids and keeps the context cap', () => {
    const { result } = renderHook(() => useContinuationSetupState(7, 12))
    act(() => {
      result.current.setContextChapters('999')
      result.current.setSelectedContextSummaryIds([9])
    })
    act(() => result.current.handleGenerate())
    expect(mockNavigate).toHaveBeenCalledWith('/novel/7?stage=results&chapter=12', {
      state: {
        novelId: 7,
        streamParams: expect.objectContaining({
          context_chapters: 5,
          context_summary_ids: [9],
          target_chars: 3000,
        }),
      },
    })
  })

  it('opens a generated draft for review without selecting it', async () => {
    mockCreate.mockResolvedValue({ ...summaryRows[0], id: 10, review_status: 'draft' })
    const { result } = renderHook(() => useContinuationSetupState(7, 12))
    act(() => result.current.setContextSummaryRange('1-10'))
    await act(async () => result.current.handleCreateContextSummary())
    expect(result.current.reviewContextSummary).toBeNull()
    expect(result.current.selectedContextSummaryIds).toEqual([])
  })

  it('validates an invalid range before generation', async () => {
    const { result } = renderHook(() => useContinuationSetupState(7, 12))
    act(() => result.current.setContextSummaryRange('20-1'))
    await act(async () => result.current.handleCreateContextSummary())
    expect(mockCreate).not.toHaveBeenCalled()
    expect(result.current.contextSummaryError).toBe(
      'continuation.setup.contextSummary.error.rangeInvalid',
    )
  })
})
