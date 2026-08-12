import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockNavigate = vi.fn()
const mockCreateOutline = vi.fn()
const mockDeleteOutline = vi.fn()
const outlineRows = [{
  id: 9,
  novel_id: 7,
  start_chapter: 1,
  end_chapter: 10,
  title: '第1—10章剧情大纲',
  content: '摘要',
  model: 'test-model',
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}]

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}))

vi.mock('@/contexts/UiLocaleContext', () => ({
  useUiLocale: () => ({
    locale: 'zh',
    t: (key: string) => key,
  }),
}))

vi.mock('@/services/api', () => ({
  api: {
    updatePreferences: vi.fn().mockResolvedValue(undefined),
  },
  ApiError: class ApiError extends Error {},
}))

vi.mock('@/hooks/novel/useNovelOutlines', () => ({
  useNovelOutlines: () => ({
    data: outlineRows,
    isLoading: false,
    isSuccess: true,
    isError: false,
  }),
  useCreateNovelOutline: () => ({
    mutateAsync: mockCreateOutline,
    isPending: false,
  }),
  useDeleteNovelOutline: () => ({
    mutateAsync: mockDeleteOutline,
    isPending: false,
    variables: undefined,
  }),
}))

import { useContinuationSetupState } from '@/hooks/novel/useContinuationSetupState'

describe('useContinuationSetupState outline integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('passes selected outline ids while preserving the five-chapter context cap', () => {
    const { result } = renderHook(() => useContinuationSetupState(7, 12))

    act(() => {
      result.current.setContextChapters('999')
      result.current.setSelectedOutlineIds([9])
    })
    act(() => result.current.handleGenerate())

    expect(mockNavigate).toHaveBeenCalledWith(
      '/novel/7?stage=results&chapter=12',
      {
        state: {
          novelId: 7,
          streamParams: expect.objectContaining({
            context_chapters: 5,
            outline_ids: [9],
            target_chars: 3000,
          }),
        },
      },
    )
  })

  it('shows a safe validation error before generating an invalid range', async () => {
    const { result } = renderHook(() => useContinuationSetupState(7, 12))

    act(() => result.current.setOutlineRange('20-1'))
    await act(async () => result.current.handleCreateOutline())

    expect(mockCreateOutline).not.toHaveBeenCalled()
    expect(result.current.outlineError).toBe('continuation.setup.outline.error.rangeInvalid')
  })
})
