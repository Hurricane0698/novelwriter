import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { getWindowIndexPollingInterval } from '@/lib/windowIndexStatus'
import type { Novel, WindowIndexState } from '@/types/api'
import { novelKeys } from './keys'

export function useNovelWindowIndex(novelId: number) {
  return useQuery<Novel, Error, WindowIndexState | null>({
    queryKey: novelKeys.detail(novelId),
    queryFn: () => api.getNovel(novelId),
    select: (novel) => novel.window_index ?? null,
    enabled: Number.isFinite(novelId) && novelId > 0,
    refetchInterval: (query) => getWindowIndexPollingInterval(query.state.data?.window_index, query.state.dataUpdateCount),
  })
}
