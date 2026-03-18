import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/services/api"
import { novelKeys } from "@/hooks/novel/keys"
import type { Chapter, ChapterMeta, Novel } from "@/types/api"

export function useDeleteChapter(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (chapterNum: number) => api.deleteChapter(novelId, chapterNum),
    onMutate: async (chapterNum) => {
      await qc.cancelQueries({ queryKey: novelKeys.chapter(novelId, chapterNum), exact: true })
      await qc.cancelQueries({ queryKey: novelKeys.chaptersMeta(novelId) })
      await qc.cancelQueries({ queryKey: novelKeys.detail(novelId) })

      const previousChapter = qc.getQueryData<Chapter>(novelKeys.chapter(novelId, chapterNum))
      const previousMeta = qc.getQueryData<ChapterMeta[]>(novelKeys.chaptersMeta(novelId))
      const previousNovel = qc.getQueryData<Novel>(novelKeys.detail(novelId))

      if (previousMeta) {
        qc.setQueryData<ChapterMeta[]>(
          novelKeys.chaptersMeta(novelId),
          previousMeta.filter((chapter) => chapter.chapter_number !== chapterNum),
        )
      }

      if (previousNovel) {
        qc.setQueryData<Novel>(novelKeys.detail(novelId), {
          ...previousNovel,
          total_chapters: Math.max(previousNovel.total_chapters - 1, 0),
        })
      }

      qc.removeQueries({ queryKey: novelKeys.chapter(novelId, chapterNum), exact: true })

      return { previousChapter, previousMeta, previousNovel }
    },
    onError: (_error, chapterNum, context) => {
      if (context?.previousChapter) {
        qc.setQueryData(novelKeys.chapter(novelId, chapterNum), context.previousChapter)
      } else {
        qc.invalidateQueries({ queryKey: novelKeys.chapter(novelId, chapterNum), exact: true })
      }
      if (context?.previousMeta) {
        qc.setQueryData(novelKeys.chaptersMeta(novelId), context.previousMeta)
      }
      if (context?.previousNovel) {
        qc.setQueryData(novelKeys.detail(novelId), context.previousNovel)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.chaptersMeta(novelId) })
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelId) })
    },
  })
}
