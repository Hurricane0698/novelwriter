import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { novelKeys } from './keys'
import { api } from '@/services/api'
import type { NovelContextSummary } from '@/types/api'

export interface ContextSummaryRange {
  startChapter: number
  endChapter: number
}

export interface ContextSummaryUpdate {
  id: number
  content: string
  reviewStatus: NovelContextSummary['review_status']
}

function sortSummaries(summaries: NovelContextSummary[]): NovelContextSummary[] {
  return [...summaries].sort((a, b) => (
    a.start_chapter - b.start_chapter
    || a.end_chapter - b.end_chapter
    || b.id - a.id
  ))
}

function upsertSummary(
  current: NovelContextSummary[] | undefined,
  summary: NovelContextSummary,
): NovelContextSummary[] {
  return sortSummaries([...(current ?? []).filter(item => item.id !== summary.id), summary])
}

export function useNovelContextSummaries(novelId: number) {
  return useQuery({
    queryKey: novelKeys.contextSummaries(novelId),
    queryFn: () => api.listContextSummaries(novelId),
    enabled: Number.isFinite(novelId) && novelId > 0,
  })
}

export function useCreateNovelContextSummary(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ startChapter, endChapter }: ContextSummaryRange) => (
      api.createContextSummary(novelId, startChapter, endChapter)
    ),
    onSuccess: (created) => {
      queryClient.setQueryData<NovelContextSummary[]>(
        novelKeys.contextSummaries(novelId),
        current => upsertSummary(current, created),
      )
    },
  })
}

export function useUpdateNovelContextSummary(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, content, reviewStatus }: ContextSummaryUpdate) => (
      api.updateContextSummary(novelId, id, {
        content,
        review_status: reviewStatus,
      })
    ),
    onSuccess: (updated) => {
      queryClient.setQueryData<NovelContextSummary[]>(
        novelKeys.contextSummaries(novelId),
        current => upsertSummary(current, updated),
      )
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: novelKeys.contextSummaries(novelId) })
    },
  })
}

export function useRegenerateNovelContextSummary(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (summaryId: number) => api.regenerateContextSummary(novelId, summaryId),
    onSuccess: (updated) => {
      queryClient.setQueryData<NovelContextSummary[]>(
        novelKeys.contextSummaries(novelId),
        current => upsertSummary(current, updated),
      )
    },
  })
}

export function useDeleteNovelContextSummary(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (summaryId: number) => api.deleteContextSummary(novelId, summaryId),
    onSuccess: (_result, summaryId) => {
      queryClient.setQueryData<NovelContextSummary[]>(
        novelKeys.contextSummaries(novelId),
        current => current?.filter(summary => summary.id !== summaryId) ?? [],
      )
    },
  })
}
