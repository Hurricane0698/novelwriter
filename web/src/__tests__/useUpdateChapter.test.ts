import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { novelKeys } from '@/hooks/novel/keys'
import { createQueryClientWrapper, createTestQueryClient } from './helpers'

vi.mock('@/services/api', () => ({
  api: {
    updateChapter: vi.fn(),
  },
}))

import { api } from '@/services/api'
import { useUpdateChapter } from '@/hooks/novel/useUpdateChapter'

const mockUpdateChapter = api.updateChapter as ReturnType<typeof vi.fn>

describe('useUpdateChapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('optimistically updates cache and then stores the server chapter (and updates meta title)', async () => {
    const novelId = 7
    const chapterNum = 3
    const payload = { title: '新标题', content: '更新后的正文' }
    const initialChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      content: '旧正文',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    const initialMeta = [{
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      created_at: '2026-02-01T00:00:00Z',
    }]
    const updatedChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: payload.title,
      content: payload.content,
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-02T00:00:00Z',
    }
    let resolveUpdate: (v: typeof updatedChapter) => void
    const updatePromise = new Promise<typeof updatedChapter>((resolve) => {
      resolveUpdate = resolve
    })
    mockUpdateChapter.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(novelId, chapterNum), initialChapter)
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), initialMeta)

    const { result } = renderHook(() => useUpdateChapter(novelId, chapterNum), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync(payload)
    })

    // Optimistic patch applied immediately (before the server promise resolves).
    await act(async () => {
      // React Query schedules mutations; flush one tick to let onMutate run.
      await Promise.resolve()
    })

    expect(mockUpdateChapter).toHaveBeenCalledWith(novelId, chapterNum, payload)
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toMatchObject({
      title: payload.title,
      content: payload.content,
    })
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toMatchObject([{
      chapter_number: chapterNum,
      title: payload.title,
    }])

    resolveUpdate!(updatedChapter)
    await act(async () => {
      await mutationPromise
    })

    // Final cache reflects the server response.
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(updatedChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toMatchObject([{
      chapter_number: chapterNum,
      title: updatedChapter.title,
    }])
  })

  it('rolls back cache on update error', async () => {
    const novelId = 7
    const chapterNum = 3
    const payload = { title: '新标题' }
    const initialChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      content: '旧正文',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    const initialMeta = [{
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      created_at: '2026-02-01T00:00:00Z',
    }]
    let rejectUpdate: (e: unknown) => void
    const updatePromise = new Promise((_resolve, reject) => {
      rejectUpdate = reject
    })
    mockUpdateChapter.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(novelId, chapterNum), initialChapter)
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), initialMeta)

    const { result } = renderHook(() => useUpdateChapter(novelId, chapterNum), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync(payload)
    })

    // Optimistic patch applied.
    await act(async () => {
      await Promise.resolve()
    })
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toMatchObject({
      title: payload.title,
    })

    rejectUpdate!(new Error('update failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('update failed')
    })

    // Rolled back to previous values.
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(initialChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual(initialMeta)
  })
})
