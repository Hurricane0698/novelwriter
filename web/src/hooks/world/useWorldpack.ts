import { useMutation, useQueryClient } from '@tanstack/react-query'
import { worldApi } from '@/services/api'
import { worldKeys } from './keys'
import type { WorldpackV1 } from '@/types/api'

export function useImportWorldpack(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: WorldpackV1) => worldApi.importWorldpack(novelId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: worldKeys.all(novelId) })
    },
  })
}
