import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { novelKeys } from '@/hooks/novel/keys'
import { createQueryClientWrapper, createTestQueryClient } from '@/__tests__/support/queryClient'

vi.mock('@/services/api', () => ({
  api: {
    updateChapter: vi.fn(),
  },
}))

import { api } from '@/services/api'
import { useUpdateChapter } from '@/hooks/novel/useUpdateChapter'
import { MARKDOWN_CHAPTER_BODY_INVALID } from '@/lib/chapterMutationError'
import { ApiError } from '@/services/apiClient'

const mockUpdateChapter = api.updateChapter as ReturnType<typeof vi.fn>

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

function savedChapter(content: string, updatedAt: string) {
  return {
    id: 99,
    novel_id: 7,
    chapter_number: 3,
    title: '第三章',
    source_chapter_label: '第3章',
    source_chapter_number: 3,
    source_volume_title: null,
    content,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: updatedAt,
  }
}

describe('useUpdateChapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps committed cache while pending and stores the server chapter on success', async () => {
    const novelId = 7
    const chapterNum = 3
    const payload = { title: '新标题', content: '更新后的正文' }
    const initialChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      source_chapter_label: '第3章 旧标题',
      source_chapter_number: 3,
      source_volume_title: null,
      content: '旧正文',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    const initialMeta = [{
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      source_chapter_label: '第3章 旧标题',
      source_chapter_number: 3,
      source_volume_title: null,
      created_at: '2026-02-01T00:00:00Z',
    }]
    const updatedChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: payload.title,
      source_chapter_label: '第3章 旧标题',
      source_chapter_number: 3,
      source_volume_title: null,
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
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries')
    queryClient.setQueryData(novelKeys.chapter(novelId, chapterNum), initialChapter)
    queryClient.setQueryData(novelKeys.chaptersMeta(novelId), initialMeta)

    const { result } = renderHook(() => useUpdateChapter(novelId, chapterNum), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync(payload)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(mockUpdateChapter).toHaveBeenCalledWith(novelId, chapterNum, payload)
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(initialChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual(initialMeta)

    resolveUpdate!(updatedChapter)
    await act(async () => {
      await mutationPromise
    })

    // Final cache reflects the server response.
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(updatedChapter)
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: novelKeys.contextSummaries(novelId),
    })
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toMatchObject([{
      chapter_number: chapterNum,
      title: updatedChapter.title,
      source_chapter_label: updatedChapter.source_chapter_label,
      source_chapter_number: updatedChapter.source_chapter_number,
    }])
  })

  it('keeps stale chapter and metadata reads from overwriting a successful update', async () => {
    const initialChapter = {
      ...savedChapter('已提交正文', '2026-02-01T00:00:00Z'),
      title: '旧标题',
      source_chapter_label: '第3章 旧标题',
    }
    const initialMeta = [{
      id: initialChapter.id,
      novel_id: initialChapter.novel_id,
      chapter_number: initialChapter.chapter_number,
      title: initialChapter.title,
      source_chapter_label: initialChapter.source_chapter_label,
      source_chapter_number: initialChapter.source_chapter_number,
      source_volume_title: initialChapter.source_volume_title,
      created_at: initialChapter.created_at,
    }]
    const updatedChapter = {
      ...initialChapter,
      title: '服务器标题',
      source_chapter_label: '第3章 服务器标题',
      content: '服务器正文',
      updated_at: '2026-02-02T00:00:00Z',
    }
    const update = deferred<typeof updatedChapter>()
    const beforeUpdateChapterRead = deferred<typeof initialChapter>()
    const beforeUpdateMetaRead = deferred<typeof initialMeta>()
    const duringUpdateChapterRead = deferred<typeof initialChapter>()
    const duringUpdateMetaRead = deferred<typeof initialMeta>()
    mockUpdateChapter.mockReturnValue(update.promise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(7, 3), initialChapter)
    queryClient.setQueryData(novelKeys.chaptersMeta(7), initialMeta)
    const { result } = renderHook(() => useUpdateChapter(7, 3), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    const beforeUpdateChapterQuery = vi.fn(() => beforeUpdateChapterRead.promise)
    const beforeUpdateMetaQuery = vi.fn(() => beforeUpdateMetaRead.promise)
    const staleFetches = [
      queryClient.fetchQuery({
        queryKey: novelKeys.chapter(7, 3),
        queryFn: beforeUpdateChapterQuery,
      }).catch(() => undefined),
      queryClient.fetchQuery({
        queryKey: novelKeys.chaptersMeta(7),
        queryFn: beforeUpdateMetaQuery,
      }).catch(() => undefined),
    ]
    expect(beforeUpdateChapterQuery).toHaveBeenCalledTimes(1)
    expect(beforeUpdateMetaQuery).toHaveBeenCalledTimes(1)

    let mutationPromise!: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({
        title: updatedChapter.title,
        content: updatedChapter.content,
      })
    })
    await waitFor(() => expect(mockUpdateChapter).toHaveBeenCalledTimes(1))

    // Reads started while the PUT is pending must also be cancelled at commit.
    const duringUpdateChapterQuery = vi.fn(() => duringUpdateChapterRead.promise)
    const duringUpdateMetaQuery = vi.fn(() => duringUpdateMetaRead.promise)
    staleFetches.push(
      queryClient.fetchQuery({
        queryKey: novelKeys.chapter(7, 3),
        queryFn: duringUpdateChapterQuery,
      }).catch(() => undefined),
      queryClient.fetchQuery({
        queryKey: novelKeys.chaptersMeta(7),
        queryFn: duringUpdateMetaQuery,
      }).catch(() => undefined),
    )
    expect(duringUpdateChapterQuery).toHaveBeenCalledTimes(1)
    expect(duringUpdateMetaQuery).toHaveBeenCalledTimes(1)

    await act(async () => {
      update.resolve(updatedChapter)
      await mutationPromise
    })
    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(updatedChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(7))).toEqual([{
      ...initialMeta[0],
      title: updatedChapter.title,
      source_chapter_label: updatedChapter.source_chapter_label,
      source_chapter_number: updatedChapter.source_chapter_number,
    }])

    await act(async () => {
      beforeUpdateChapterRead.resolve(initialChapter)
      beforeUpdateMetaRead.resolve(initialMeta)
      duringUpdateChapterRead.resolve(initialChapter)
      duringUpdateMetaRead.resolve(initialMeta)
      await Promise.all([
        beforeUpdateChapterRead.promise,
        beforeUpdateMetaRead.promise,
        duringUpdateChapterRead.promise,
        duringUpdateMetaRead.promise,
      ])
      await Promise.resolve()
    })
    await Promise.all(staleFetches)

    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(updatedChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(7))).toEqual([{
      ...initialMeta[0],
      title: updatedChapter.title,
      source_chapter_label: updatedChapter.source_chapter_label,
      source_chapter_number: updatedChapter.source_chapter_number,
    }])
  })

  it('keeps the last committed cache snapshot on update error', async () => {
    const novelId = 7
    const chapterNum = 3
    const payload = { title: '新标题' }
    const initialChapter = {
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      source_chapter_label: '第3章 旧标题',
      source_chapter_number: 3,
      source_volume_title: null,
      content: '旧正文',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: null,
    }
    const initialMeta = [{
      id: 99,
      novel_id: novelId,
      chapter_number: chapterNum,
      title: '旧标题',
      source_chapter_label: '第3章 旧标题',
      source_chapter_number: 3,
      source_volume_title: null,
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

    await act(async () => {
      await Promise.resolve()
    })
    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(initialChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual(initialMeta)

    rejectUpdate!(new Error('update failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('update failed')
    })

    expect(queryClient.getQueryData(novelKeys.chapter(novelId, chapterNum))).toEqual(initialChapter)
    expect(queryClient.getQueryData(novelKeys.chaptersMeta(novelId))).toEqual(initialMeta)
  })

  it('sends invalid Markdown to the API and propagates its structured rejection', async () => {
    const payload = { content: '# Injected volume' }
    const error = new ApiError(422, 'HTTP 422', {
      code: MARKDOWN_CHAPTER_BODY_INVALID,
      detail: { code: MARKDOWN_CHAPTER_BODY_INVALID },
    })
    mockUpdateChapter.mockRejectedValue(error)
    const { result } = renderHook(() => useUpdateChapter(7, 3), {
      wrapper: createQueryClientWrapper(createTestQueryClient()),
    })

    await expect(result.current.mutateAsync(payload)).rejects.toBe(error)
    expect(mockUpdateChapter).toHaveBeenCalledWith(7, 3, payload)
  })

  it('serializes updates for the same chapter and keeps the second response in cache', async () => {
    const first = deferred<ReturnType<typeof savedChapter>>()
    const second = deferred<ReturnType<typeof savedChapter>>()
    const firstPayload = { content: '第一次输入' }
    const secondPayload = { content: '第二次输入' }
    const firstSaved = savedChapter(firstPayload.content, '2026-02-02T00:00:00Z')
    const secondSaved = savedChapter(secondPayload.content, '2026-02-03T00:00:00Z')
    mockUpdateChapter
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(7, 3), savedChapter('旧正文', '2026-02-01T00:00:00Z'))
    const { result } = renderHook(() => useUpdateChapter(7, 3), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let firstMutation!: Promise<unknown>
    let secondMutation!: Promise<unknown>
    act(() => {
      firstMutation = result.current.mutateAsync(firstPayload)
      secondMutation = result.current.mutateAsync(secondPayload)
    })
    await act(async () => {
      await Promise.resolve()
    })

    expect(mockUpdateChapter).toHaveBeenCalledTimes(1)
    expect(mockUpdateChapter).toHaveBeenNthCalledWith(1, 7, 3, firstPayload)

    await act(async () => {
      first.resolve(firstSaved)
      await firstMutation
    })
    await waitFor(() => expect(mockUpdateChapter).toHaveBeenCalledTimes(2))
    expect(mockUpdateChapter).toHaveBeenNthCalledWith(2, 7, 3, secondPayload)

    await act(async () => {
      second.resolve(secondSaved)
      await secondMutation
    })

    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(secondSaved)
  })

  it('continues the next scoped update after the previous update fails', async () => {
    const first = deferred<ReturnType<typeof savedChapter>>()
    const second = deferred<ReturnType<typeof savedChapter>>()
    const firstPayload = { content: '会失败的输入' }
    const secondPayload = { content: '失败后的新输入' }
    const secondSaved = savedChapter(secondPayload.content, '2026-02-03T00:00:00Z')
    const firstError = new Error('first update failed')
    mockUpdateChapter
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(7, 3), savedChapter('旧正文', '2026-02-01T00:00:00Z'))
    const { result } = renderHook(() => useUpdateChapter(7, 3), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let firstMutation!: Promise<unknown>
    let secondMutation!: Promise<unknown>
    act(() => {
      firstMutation = result.current.mutateAsync(firstPayload)
      secondMutation = result.current.mutateAsync(secondPayload)
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(mockUpdateChapter).toHaveBeenCalledTimes(1)

    await act(async () => {
      first.reject(firstError)
      await expect(firstMutation).rejects.toBe(firstError)
    })
    await waitFor(() => expect(mockUpdateChapter).toHaveBeenCalledTimes(2))
    expect(mockUpdateChapter).toHaveBeenNthCalledWith(2, 7, 3, secondPayload)

    await act(async () => {
      second.resolve(secondSaved)
      await secondMutation
    })

    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(secondSaved)
  })

  it('keeps the last committed cache snapshot when consecutive scoped updates both fail', async () => {
    const first = deferred<ReturnType<typeof savedChapter>>()
    const second = deferred<ReturnType<typeof savedChapter>>()
    const firstPayload = { content: '第一次失败输入' }
    const secondPayload = { content: '第二次失败输入' }
    const firstError = new Error('first update failed')
    const secondError = new Error('second update failed')
    mockUpdateChapter
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const committedChapter = savedChapter('已提交正文', '2026-02-01T00:00:00Z')
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(novelKeys.chapter(7, 3), committedChapter)
    const { result } = renderHook(() => useUpdateChapter(7, 3), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let firstMutation!: Promise<unknown>
    let secondMutation!: Promise<unknown>
    act(() => {
      firstMutation = result.current.mutateAsync(firstPayload)
      secondMutation = result.current.mutateAsync(secondPayload)
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(mockUpdateChapter).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(committedChapter)

    await act(async () => {
      first.reject(firstError)
      await expect(firstMutation).rejects.toBe(firstError)
    })
    await waitFor(() => expect(mockUpdateChapter).toHaveBeenCalledTimes(2))
    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(committedChapter)

    await act(async () => {
      second.reject(secondError)
      await expect(secondMutation).rejects.toBe(secondError)
    })

    expect(queryClient.getQueryData(novelKeys.chapter(7, 3))).toEqual(committedChapter)
  })
})
