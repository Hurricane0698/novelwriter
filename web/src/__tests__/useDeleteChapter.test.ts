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

  it('optimistically removes chapter from metadata and invalidates chapter metadata list + novel detail', async () => {
    const novelId = 7
    const chapterNum = 4
    let resolveDelete: (() => void) | null = null
    mockDeleteChapter.mockReturnValue(new Promise<void>((resolve) => {
      resolveDelete = resolve
    }))

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), [
      {
        id: 41,
        novel_id: novelId,
        chapter_number: 4,
        title: '第844章 归来',
        source_chapter_label: '第844章 归来',
        source_chapter_number: 844,
        created_at: '2026-02-01T00:00:00Z',
      },
      {
        id: 42,
        novel_id: novelId,
        chapter_number: 5,
        title: '第845章 新章',
        source_chapter_label: '第845章 新章',
        source_chapter_number: 845,
        created_at: '2026-02-02T00:00:00Z',
      },
    ])
    queryClient.setQueryData(novelKeys.detail(novelId), {
      id: novelId,
      title: '测试小说',
      author: '作者',
      total_chapters: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-31T00:00:00Z',
    })
    queryClient.setQueryData(novelKeys.chapter(novelId, chapterNum), {
      id: 41,
      novel_id: novelId,
      chapter_number: 4,
      title: '归来',
      source_chapter_label: '第844章 归来',
      source_chapter_number: 844,
      content: '章节内容',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    })

    const { result } = renderHook(() => useDeleteChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    await act(async () => {
      mutationPromise = result.current.mutateAsync(chapterNum)
      await Promise.resolve()
    })

    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual([
      {
        id: 42,
        novel_id: novelId,
        chapter_number: 5,
        title: '第845章 新章',
        source_chapter_label: '第845章 新章',
        source_chapter_number: 845,
        created_at: '2026-02-02T00:00:00Z',
      },
    ])
    expect(queryClient.getQueryData(novelKeys.detail(novelId))).toMatchObject({ total_chapters: 1 })
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toBeUndefined()

    resolveDelete!()
    await act(async () => {
      await mutationPromise!
    })

    expect(mockDeleteChapter).toHaveBeenCalledWith(novelId, chapterNum)
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.chaptersMeta(novelId) })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.detail(novelId) })
  })

  it('rolls back optimistic delete on error', async () => {
    const novelId = 7
    const chapterNum = 4
    let rejectDelete: ((error: unknown) => void) | null = null
    mockDeleteChapter.mockReturnValue(new Promise((_, reject) => {
      rejectDelete = reject
    }))

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const initialMeta = [
      {
        id: 41,
        novel_id: novelId,
        chapter_number: 4,
        title: '第844章 归来',
        source_chapter_label: '第844章 归来',
        source_chapter_number: 844,
        created_at: '2026-02-01T00:00:00Z',
      },
    ]
    const initialNovel = {
      id: novelId,
      title: '测试小说',
      author: '作者',
      language: 'zh',
      total_chapters: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-31T00:00:00Z',
    }
    const initialChapter = {
      id: 41,
      novel_id: novelId,
      chapter_number: 4,
      title: '归来',
      source_chapter_label: '第844章 归来',
      source_chapter_number: 844,
      content: '章节内容',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), initialMeta)
    queryClient.setQueryData(novelKeys.detail(novelId), initialNovel)
    queryClient.setQueryData(novelKeys.chapter(novelId, chapterNum), initialChapter)

    const { result } = renderHook(() => useDeleteChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    await act(async () => {
      mutationPromise = result.current.mutateAsync(chapterNum)
      await Promise.resolve()
    })

    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual([])
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toBeUndefined()

    rejectDelete!(new Error('delete failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('delete failed')
    })

    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(initialChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual(initialMeta)
    expect(queryClient.getQueryData(novelKeys.detail(novelId))).toEqual(initialNovel)
    expect(invalidateQueriesSpy).not.toHaveBeenCalled()
  })
})
