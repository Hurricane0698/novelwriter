import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { worldApi, ApiError } from '@/services/api'
import { worldKeys } from './keys'
import { getWaitingPollInterval } from '@/lib/windowIndexStatus'
import { isBootstrapStatusRunning } from '@/lib/bootstrapStatus'
import type { BootstrapJobResponse, BootstrapTriggerRequest } from '@/types/api'

// Query identity shares ownership across observers and remounts, while cache eviction
// releases the stamp. New terminal revisions still refresh the same novel.
const terminalRefreshes = new WeakMap<object, string>()

function refreshTerminalWorldQueries(qc: QueryClient, novelId: number) {
  const query = qc.getQueryCache().find<BootstrapJobResponse | null>({
    queryKey: worldKeys.bootstrapStatus(novelId),
    exact: true,
  })
  if (!query) return

  // Read the current cache, not a potentially superseded observer render.
  const data = query.state.data
  if (!data || isBootstrapStatusRunning(data.status)) {
    terminalRefreshes.delete(query)
    return
  }
  const revision = `${data.job_id}:${data.status}:${data.updated_at}`
  if (terminalRefreshes.get(query) === revision) return
  terminalRefreshes.set(query, revision)

  void qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
  void qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
  void qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) })
}

interface UseBootstrapStatusOptions {
  refetchWhenMissing?: boolean
}

export function useBootstrapStatus(novelId: number, options: UseBootstrapStatusOptions = {}) {
  const qc = useQueryClient()
  const bootstrapQuery = useQuery({
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
      if (data?.status === 'pending') return getWaitingPollInterval(query.state.dataUpdateCount)
      if (data && isBootstrapStatusRunning(data.status)) return 2000
      if (options.refetchWhenMissing && data === null) return getWaitingPollInterval(query.state.dataUpdateCount)
      return false
    },
  })

  useEffect(() => {
    refreshTerminalWorldQueries(qc, novelId)
  }, [bootstrapQuery.data, novelId, qc])

  return bootstrapQuery
}

export function useTriggerBootstrap(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: BootstrapTriggerRequest) => worldApi.triggerBootstrap(novelId, payload),
    onSuccess: (data) => {
      qc.setQueryData(worldKeys.bootstrapStatus(novelId), data)
      refreshTerminalWorldQueries(qc, novelId)
      if (isBootstrapStatusRunning(data.status)) {
        void qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
        void qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
      }
    },
  })
}
