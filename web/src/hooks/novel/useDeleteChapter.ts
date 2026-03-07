import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/services/api"
import { novelKeys } from "@/hooks/novel/keys"

export function useDeleteChapter(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (chapterNum: number) => api.deleteChapter(novelId, chapterNum),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.chaptersMeta(novelId) })
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelId) })
    },
  })
}
