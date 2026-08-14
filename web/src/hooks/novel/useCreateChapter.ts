import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import type { Chapter, ChapterCreateRequest, ChapterMeta, Novel } from '@/types/api'

export function useCreateChapter(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChapterCreateRequest) => api.createChapter(novelId, data),
    onSuccess: (created) => {
      qc.setQueryData<Chapter>(novelKeys.chapter(novelId, created.chapter_number), created)
      qc.setQueryData<ChapterMeta[]>(novelKeys.chaptersMeta(novelId), (old) => {
        if (!old) return old
        const nextMeta = {
          id: created.id,
          novel_id: created.novel_id,
          chapter_number: created.chapter_number,
          title: created.title,
          source_chapter_label: created.source_chapter_label,
          source_chapter_number: created.source_chapter_number,
          source_volume_title: created.source_volume_title,
          created_at: created.created_at,
        }
        const filtered = old.filter((meta) => meta.chapter_number !== created.chapter_number)
        return [...filtered, nextMeta].sort((a, b) => a.chapter_number - b.chapter_number)
      })
      qc.setQueryData<Novel>(novelKeys.detail(novelId), (old) => {
        if (!old) return old
        return {
          ...old,
          total_chapters: old.total_chapters + 1,
        }
      })
      qc.invalidateQueries({ queryKey: novelKeys.chaptersMeta(novelId) })
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelId) })
      qc.invalidateQueries({ queryKey: novelKeys.contextSummaries(novelId) })
    },
  })
}
