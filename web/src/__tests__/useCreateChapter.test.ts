import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { novelKeys } from '@/hooks/novel/keys'
import { createQueryClientWrapper, createTestQueryClient } from '@/__tests__/support/queryClient'

vi.mock('@/services/api', () => ({
  api: {
    createChapter: vi.fn(),
  },
}))

import { api } from '@/services/api'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import { MARKDOWN_CHAPTER_BODY_INVALID } from '@/lib/chapterMutationError'
import { ApiError } from '@/services/apiClient'

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
      source_chapter_label: null,
      source_chapter_number: null,
      source_volume_title: null,
      content: payload.content,
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    mockCreateChapter.mockResolvedValue(createdChapter)

    const queryClient = createTestQueryClient()
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), [
      {
        id: 99,
        novel_id: novelId,
        chapter_number: 3,
        title: '旧第三章',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        created_at: '2026-01-31T00:00:00Z',
      },
    ])
    queryClient.setQueryData(novelKeys.detail(novelId), {
      id: novelId,
      title: '测试小说',
      author: '作者',
      total_chapters: 3,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-31T00:00:00Z',
    })

    const { result } = renderHook(() => useCreateChapter(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationResult: unknown
    await act(async () => {
      mutationResult = await result.current.mutateAsync(payload)
    })

    expect(mockCreateChapter).toHaveBeenCalledWith(novelId, payload)
    expect(mutationResult).toEqual(createdChapter)
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, 4))).toEqual(createdChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual([
      {
        id: 99,
        novel_id: novelId,
        chapter_number: 3,
        title: '旧第三章',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        created_at: '2026-01-31T00:00:00Z',
      },
      {
        id: 101,
        novel_id: novelId,
        chapter_number: 4,
        title: '新章',
        source_chapter_label: null,
        source_chapter_number: null,
        source_volume_title: null,
        created_at: '2026-02-01T00:00:00Z',
      },
    ])
    expect(queryClient.getQueryData(novelKeys.detail(novelId))).toMatchObject({ total_chapters: 4 })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.chaptersMeta(novelId) })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: novelKeys.detail(novelId) })
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: novelKeys.contextSummaries(novelId),
    })
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

  it('sends invalid Markdown to the API and propagates its structured rejection', async () => {
    const payload = { content: '## Injected chapter' }
    const error = new ApiError(422, 'HTTP 422', {
      code: MARKDOWN_CHAPTER_BODY_INVALID,
      detail: { code: MARKDOWN_CHAPTER_BODY_INVALID },
    })
    mockCreateChapter.mockRejectedValue(error)
    const { result } = renderHook(() => useCreateChapter(7), {
      wrapper: createQueryClientWrapper(createTestQueryClient()),
    })

    await expect(result.current.mutateAsync(payload)).rejects.toBe(error)
    expect(mockCreateChapter).toHaveBeenCalledWith(7, payload)
  })
})
