import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { novelKeys } from './keys'
import { api } from '@/services/api'
import type { NovelOutline } from '@/types/api'

export interface NovelOutlineRange {
  startChapter: number
  endChapter: number
}

function sortOutlines(outlines: NovelOutline[]): NovelOutline[] {
  return [...outlines].sort((a, b) => (
    a.start_chapter - b.start_chapter
    || a.end_chapter - b.end_chapter
    || b.id - a.id
  ))
}

export function useNovelOutlines(novelId: number) {
  return useQuery({
    queryKey: novelKeys.outlines(novelId),
    queryFn: () => api.listOutlines(novelId),
    enabled: Number.isFinite(novelId) && novelId > 0,
  })
}

export function useCreateNovelOutline(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ startChapter, endChapter }: NovelOutlineRange) => (
      api.createOutline(novelId, startChapter, endChapter)
    ),
    onSuccess: (created) => {
      queryClient.setQueryData<NovelOutline[]>(novelKeys.outlines(novelId), (current) => (
        sortOutlines([...(current ?? []).filter(outline => outline.id !== created.id), created])
      ))
    },
  })
}

export function useDeleteNovelOutline(novelId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (outlineId: number) => api.deleteOutline(novelId, outlineId),
    onSuccess: (_result, outlineId) => {
      queryClient.setQueryData<NovelOutline[]>(novelKeys.outlines(novelId), (current) => (
        current?.filter(outline => outline.id !== outlineId) ?? []
      ))
    },
  })
}
