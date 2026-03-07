import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import type { Chapter, ChapterMeta, ChapterUpdateRequest } from '@/types/api'

function applyChapterPatch(prev: Chapter, patch: ChapterUpdateRequest): Chapter {
  const next = { ...prev }
  if (patch.title !== undefined) next.title = patch.title
  if (patch.content !== undefined) next.content = patch.content
  return next
}

export function useUpdateChapter(novelId: number, chapterNum: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChapterUpdateRequest) => api.updateChapter(novelId, chapterNum, data),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: novelKeys.chapter(novelId, chapterNum) })
      await qc.cancelQueries({ queryKey: novelKeys.chaptersMeta(novelId) })

      const previousChapter = qc.getQueryData<Chapter>(novelKeys.chapter(novelId, chapterNum))
      const previousMeta = qc.getQueryData<ChapterMeta[]>(novelKeys.chaptersMeta(novelId))

      if (previousChapter) {
        qc.setQueryData<Chapter>(novelKeys.chapter(novelId, chapterNum), applyChapterPatch(previousChapter, patch))
      }

      if (previousMeta && patch.title !== undefined) {
        qc.setQueryData<ChapterMeta[]>(
          novelKeys.chaptersMeta(novelId),
          previousMeta.map((m) => (m.chapter_number === chapterNum ? { ...m, title: patch.title ?? '' } : m)),
        )
      }

      return { previousChapter, previousMeta }
    },
    onError: (_err, _patch, context) => {
      if (context?.previousChapter) {
        qc.setQueryData(novelKeys.chapter(novelId, chapterNum), context.previousChapter)
      }
      if (context?.previousMeta) {
        qc.setQueryData(novelKeys.chaptersMeta(novelId), context.previousMeta)
      }
    },
    onSuccess: (updated) => {
      qc.setQueryData<Chapter>(novelKeys.chapter(novelId, chapterNum), updated)
      qc.setQueryData<ChapterMeta[]>(novelKeys.chaptersMeta(novelId), (old) => {
        if (!old) return old
        return old.map((m) => (m.chapter_number === chapterNum ? { ...m, title: updated.title } : m))
      })
    },
  })
}
