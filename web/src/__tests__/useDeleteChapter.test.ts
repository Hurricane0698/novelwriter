import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { novelKeys } from '@/hooks/novel/keys'
import { createQueryClientWrapper, createTestQueryClient } from './helpers'

vi.mock('@/services/api', () => ({
  api: {
    deleteChapter: vi.fn(),
  },
}))

import { api } from '@/services/api'
import { useDeleteChapter } from '@/hooks/novel/useDeleteChapter'

const mockDeleteChapter = api.deleteChapter as ReturnType<typeof vi.fn>

describe('useDeleteChapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deletes chapter and invalidates chapter metadata list + novel detail', async () => {
    const novelId = 7
    const chapterNum = 4
    mockDeleteChapter.mockResolvedValue(undefined)

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useDeleteChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(chapterNum)
    })

    expect(mockDeleteChapter).toHaveBeenCalledWith(novelId, chapterNum)
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.chaptersMeta(novelId) })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.detail(novelId) })
  })

  it('rethrows delete error and does not invalidate queries', async () => {
    const novelId = 7
    const chapterNum = 4
    mockDeleteChapter.mockRejectedValue(new Error('delete failed'))

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useDeleteChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    await expect(result.current.mutateAsync(chapterNum)).rejects.toThrow('delete failed')
    expect(invalidateQueriesSpy).not.toHaveBeenCalled()
  })
})
