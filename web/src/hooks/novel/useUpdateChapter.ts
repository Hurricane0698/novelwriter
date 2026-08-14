import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import type { Chapter, ChapterMeta, ChapterUpdateRequest } from '@/types/api'

export function useUpdateChapter(
  novelId: number,
  chapterNum: number,
) {
  const qc = useQueryClient()
  const cancelChapterReadQueries = () => Promise.all([
    qc.cancelQueries({
      queryKey: novelKeys.chapter(novelId, chapterNum),
      exact: true,
    }),
    qc.cancelQueries({
      queryKey: novelKeys.chaptersMeta(novelId),
      exact: true,
    }),
  ])

  return useMutation({
    scope: { id: `novel:${novelId}:chapter:${chapterNum}:update` },
    mutationFn: async (data: ChapterUpdateRequest) => {
      await cancelChapterReadQueries()
      return api.updateChapter(novelId, chapterNum, data)
    },
    onSuccess: async (updated) => {
      await cancelChapterReadQueries()
      qc.setQueryData<Chapter>(novelKeys.chapter(novelId, chapterNum), updated)
      qc.setQueryData<ChapterMeta[]>(novelKeys.chaptersMeta(novelId), (old) => {
        if (!old) return old
        return old.map((m) => (
          m.chapter_number === chapterNum
            ? {
                ...m,
                title: updated.title,
                source_chapter_label: updated.source_chapter_label,
                source_chapter_number: updated.source_chapter_number,
              }
            : m
        ))
      })
      await qc.invalidateQueries({ queryKey: novelKeys.contextSummaries(novelId) })
    },
  })
}
