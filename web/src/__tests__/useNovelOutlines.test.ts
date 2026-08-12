import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { novelKeys } from '@/hooks/novel/keys'
import {
  useCreateNovelOutline,
  useDeleteNovelOutline,
  useNovelOutlines,
} from '@/hooks/novel/useNovelOutlines'
import { createQueryClientWrapper, createTestQueryClient } from '@/__tests__/support/queryClient'

vi.mock('@/services/api', () => ({
  api: {
    listOutlines: vi.fn(),
    createOutline: vi.fn(),
    deleteOutline: vi.fn(),
  },
}))

import { api } from '@/services/api'

const mockListOutlines = api.listOutlines as ReturnType<typeof vi.fn>
const mockCreateOutline = api.createOutline as ReturnType<typeof vi.fn>
const mockDeleteOutline = api.deleteOutline as ReturnType<typeof vi.fn>

function outline(id: number, startChapter: number, endChapter: number) {
  return {
    id,
    novel_id: 7,
    start_chapter: startChapter,
    end_chapter: endChapter,
    title: `第${startChapter}—${endChapter}章剧情大纲`,
    content: `摘要 ${id}`,
    model: 'test-model',
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
  }
}

describe('novel outline hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads outlines as server state under a novel-scoped query key', async () => {
    mockListOutlines.mockResolvedValue([outline(1, 1, 20)])
    const queryClient = createTestQueryClient()
    const { result } = renderHook(() => useNovelOutlines(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockListOutlines).toHaveBeenCalledWith(7)
    expect(queryClient.getQueryData(novelKeys.outlines(7))).toEqual([outline(1, 1, 20)])
  })

  it('adds a generated outline to sorted query state', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.outlines(7), [outline(2, 21, 40)])
    mockCreateOutline.mockResolvedValue(outline(1, 1, 20))
    const { result } = renderHook(() => useCreateNovelOutline(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ startChapter: 1, endChapter: 20 })
    })

    expect(mockCreateOutline).toHaveBeenCalledWith(7, 1, 20)
    expect(queryClient.getQueryData(novelKeys.outlines(7))).toEqual([
      outline(1, 1, 20),
      outline(2, 21, 40),
    ])
  })

  it('removes a deleted outline only after the server succeeds', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.outlines(7), [outline(1, 1, 20), outline(2, 21, 40)])
    mockDeleteOutline.mockResolvedValue(undefined)
    const { result } = renderHook(() => useDeleteNovelOutline(7), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockDeleteOutline).toHaveBeenCalledWith(7, 1)
    expect(queryClient.getQueryData(novelKeys.outlines(7))).toEqual([outline(2, 21, 40)])
  })
})
