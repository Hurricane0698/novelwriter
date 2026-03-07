import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/services/api"
import { novelKeys } from "@/hooks/novel/keys"
import type { ChapterCreateRequest } from "@/types/api"

export function useCreateChapter(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChapterCreateRequest) => api.createChapter(novelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.chaptersMeta(novelId) })
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelId) })
    },
  })
}
