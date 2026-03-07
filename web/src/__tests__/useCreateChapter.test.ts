import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { novelKeys } from '@/hooks/novel/keys'
import { createQueryClientWrapper, createTestQueryClient } from './helpers'

vi.mock('@/services/api', () => ({
  api: {
    createChapter: vi.fn(),
  },
}))

import { api } from '@/services/api'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'

const mockCreateChapter = api.createChapter as ReturnType<typeof vi.fn>

describe('useCreateChapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('creates chapter and invalidates chapter list metadata + novel detail', async () => {
    const novelId = 7
    const payload = { title: '新章', content: '章节内容' }
    const createdChapter = {
      id: 101,
      novel_id: novelId,
      chapter_number: 4,
      title: payload.title,
      content: payload.content,
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    mockCreateChapter.mockResolvedValue(createdChapter)

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useCreateChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationResult: unknown
    await act(async () => {
      mutationResult = await result.current.mutateAsync(payload)
    })

    expect(mockCreateChapter).toHaveBeenCalledWith(novelId, payload)
    expect(mutationResult).toEqual(createdChapter)
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.chaptersMeta(novelId) })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.detail(novelId) })
  })

  it('rethrows create error and does not invalidate queries', async () => {
    const novelId = 7
    const payload = { title: '新章', content: '章节内容' }
    const error = new Error('create failed')
    mockCreateChapter.mockRejectedValue(error)

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useCreateChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await expect(result.current.mutateAsync(payload)).rejects.toThrow('create failed')
    expect(invalidateQueriesSpy).not.toHaveBeenCalled()
  })
})
