import { useMutation, useQueryClient } from '@tanstack/react-query'
import { worldApi } from '@/services/api'
import { worldKeys } from './keys'
import type { WorldGenerateRequest } from '@/types/api'

export function useGenerateWorld(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WorldGenerateRequest) => worldApi.generateWorld(novelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: worldKeys.all(novelId) })
    },
  })
}
