import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { worldApi, ApiError } from '@/services/api'
import { worldKeys } from './keys'
import type { BootstrapStatus, BootstrapTriggerRequest } from '@/types/api'

const RUNNING_STATUSES: BootstrapStatus[] = ['pending', 'tokenizing', 'extracting', 'windowing', 'refining']

function isRunning(status: BootstrapStatus): boolean {
  return RUNNING_STATUSES.includes(status)
}

export function useBootstrapStatus(novelId: number) {
  return useQuery({
    queryKey: worldKeys.bootstrapStatus(novelId),
    queryFn: async () => {
      try {
        return await worldApi.getBootstrapStatus(novelId)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404 && err.code === 'bootstrap_job_not_found') {
          return null
        }
        throw err
      }
    },
    enabled: Number.isFinite(novelId) && novelId > 0,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && isRunning(data.status)) return 2000
      return false
    },
  })
}

export function useTriggerBootstrap(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: BootstrapTriggerRequest) => worldApi.triggerBootstrap(novelId, payload),
    onSuccess: (data) => {
      qc.setQueryData(worldKeys.bootstrapStatus(novelId), data)
      qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
      qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
    },
  })
}
