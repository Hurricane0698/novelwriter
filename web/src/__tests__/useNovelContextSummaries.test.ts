import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { novelKeys } from '@/hooks/novel/keys'
import {
  useCreateNovelContextSummary,
  useDeleteNovelContextSummary,
  useNovelContextSummaries,
  useRegenerateNovelContextSummary,
  useUpdateNovelContextSummary,
} from '@/hooks/novel/useNovelContextSummaries'
import { createQueryClientWrapper, createTestQueryClient } from '@/__tests__/support/queryClient'

vi.mock('@/services/api', () => ({
  api: {
    listContextSummaries: vi.fn(),
    createContextSummary: vi.fn(),
    updateContextSummary: vi.fn(),
    regenerateContextSummary: vi.fn(),
    deleteContextSummary: vi.fn(),
  },
}))

import { api } from '@/services/api'

const mockList = vi.mocked(api.listContextSummaries)
const mockCreate = vi.mocked(api.createContextSummary)
const mockUpdate = vi.mocked(api.updateContextSummary)
const mockRegenerate = vi.mocked(api.regenerateContextSummary)
const mockDelete = vi.mocked(api.deleteContextSummary)

function summary(
  id: number,
  startChapter: number,
  endChapter: number,
  reviewStatus: 'draft' | 'confirmed' = 'draft',
) {
  return {
    id,
    novel_id: 7,
    start_chapter: startChapter,
    end_chapter: endChapter,
    title: `第${startChapter}—${endChapter}章远期剧情回顾`,
    content: `摘要 ${id}`,
    model: 'test-model',
    review_status: reviewStatus,
    is_stale: false,
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
  }
}

describe('novel context summary hooks', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads summaries under a novel-scoped query key', async () => {
    mockList.mockResolvedValue([summary(1, 1, 20)])
    const queryClient = createTestQueryClient()
    const { result } = renderHook(() => useNovelContextSummaries(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockList).toHaveBeenCalledWith(7)
    expect(queryClient.getQueryData(novelKeys.contextSummaries(7))).toEqual([summary(1, 1, 20)])
  })

  it('upserts created, edited, and regenerated summaries', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.contextSummaries(7), [summary(2, 21, 40)])
    mockCreate.mockResolvedValue(summary(1, 1, 20))
    const create = renderHook(() => useCreateNovelContextSummary(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })
    await act(async () => create.result.current.mutateAsync({ startChapter: 1, endChapter: 20 }))
    expect(mockCreate).toHaveBeenCalledWith(7, 1, 20)

    const confirmed = summary(1, 1, 20, 'confirmed')
    mockUpdate.mockResolvedValue(confirmed)
    const update = renderHook(() => useUpdateNovelContextSummary(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })
    await act(async () => update.result.current.mutateAsync({
      id: 1,
      content: confirmed.content,
      reviewStatus: 'confirmed',
    }))
    expect(mockUpdate).toHaveBeenCalledWith(7, 1, {
      content: confirmed.content,
      review_status: 'confirmed',
    })

    const regenerated = { ...summary(1, 1, 20), content: '新回顾' }
    mockRegenerate.mockResolvedValue(regenerated)
    const regenerate = renderHook(() => useRegenerateNovelContextSummary(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })
    await act(async () => regenerate.result.current.mutateAsync(1))
    expect(queryClient.getQueryData(novelKeys.contextSummaries(7))).toEqual([
      regenerated,
      summary(2, 21, 40),
    ])
  })

  it('removes a summary only after the server succeeds', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.contextSummaries(7), [summary(1, 1, 20), summary(2, 21, 40)])
    mockDelete.mockResolvedValue(undefined)
    const { result } = renderHook(() => useDeleteNovelContextSummary(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })
    await act(async () => result.current.mutateAsync(1))
    expect(mockDelete).toHaveBeenCalledWith(7, 1)
    expect(queryClient.getQueryData(novelKeys.contextSummaries(7))).toEqual([summary(2, 21, 40)])
  })
})
