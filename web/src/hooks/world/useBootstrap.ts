import { useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { worldApi, ApiError } from '@/services/api'
import { worldKeys } from './keys'
import { getWaitingPollInterval } from '@/lib/windowIndexStatus'
import type { BootstrapStatus, BootstrapTriggerRequest } from '@/types/api'

const RUNNING_STATUSES: BootstrapStatus[] = ['pending', 'tokenizing', 'extracting', 'windowing', 'refining']

function isRunning(status: BootstrapStatus): boolean {
  return RUNNING_STATUSES.includes(status)
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
      if (data && isRunning(data.status)) return 2000
      if (options.refetchWhenMissing && data === null) return getWaitingPollInterval(query.state.dataUpdateCount)
      return false
    },
  })

  const lastTerminalRefreshKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const data = bootstrapQuery.data
    if (!data || isRunning(data.status)) return

    const refreshKey = `${data.job_id}:${data.status}:${data.updated_at}`
    if (lastTerminalRefreshKeyRef.current === refreshKey) return
    lastTerminalRefreshKeyRef.current = refreshKey

    qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
    qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
    qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) })
  }, [bootstrapQuery.data, novelId, qc])

  return bootstrapQuery
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
