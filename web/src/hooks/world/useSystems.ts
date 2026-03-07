import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { worldApi } from '@/services/api'
import { worldKeys } from './keys'
import { useToast } from '@/components/world-model/shared/useToast'
import { LABELS } from '@/constants/labels'
import type { CreateSystemRequest, UpdateSystemRequest, WorldSystem } from '@/types/api'

function applySystemPatch(prev: WorldSystem, patch: UpdateSystemRequest): WorldSystem {
  const next = { ...prev }
  if (patch.name !== undefined) next.name = patch.name
  if (patch.display_type !== undefined) next.display_type = patch.display_type
  if (patch.description !== undefined) next.description = patch.description
  if (patch.data !== undefined) next.data = patch.data
  if (patch.constraints !== undefined) next.constraints = patch.constraints
  if (patch.visibility !== undefined) next.visibility = patch.visibility
  return next
}

export function useWorldSystems(
  novelId: number,
  params?: {
    q?: string
    origin?: string
    worldpack_pack_id?: string
    visibility?: string
    status?: string
    display_type?: string
  },
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: [...worldKeys.systems(novelId), params],
    queryFn: () => worldApi.listSystems(novelId, params),
    enabled: enabled && Number.isFinite(novelId) && novelId > 0,
  })
}

export function useWorldSystem(novelId: number, systemId: number | null) {
  return useQuery({
    queryKey: worldKeys.system(novelId, systemId!),
    queryFn: () => worldApi.getSystem(novelId, systemId!),
    enabled: systemId !== null,
  })
}

export function useCreateSystem(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateSystemRequest) => worldApi.createSystem(novelId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) }) },
  })
}

export function useUpdateSystem(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: ({ systemId, data }: { systemId: number; data: UpdateSystemRequest }) =>
      worldApi.updateSystem(novelId, systemId, data),
    onMutate: async ({ systemId, data }) => {
      await qc.cancelQueries({ queryKey: worldKeys.system(novelId, systemId) })
      await qc.cancelQueries({ queryKey: worldKeys.systems(novelId) })

      const previousSystem = qc.getQueryData<WorldSystem>(worldKeys.system(novelId, systemId))
      // NOTE: worldKeys.systems(...) is a prefix for both list and detail keys:
      // - list:   ['world', novelId, 'systems', params]
      // - detail: ['world', novelId, 'systems', systemId]
      // Guard with `predicate` so we only snapshot list queries here.
      const previousSystemLists = qc.getQueriesData<WorldSystem[]>({
        queryKey: worldKeys.systems(novelId),
        predicate: (q) => Array.isArray(q.state.data),
      })

      if (previousSystem) {
        qc.setQueryData<WorldSystem>(
          worldKeys.system(novelId, systemId),
          applySystemPatch(previousSystem, data),
        )
      }

      qc.setQueriesData<WorldSystem[]>(
        {
          queryKey: worldKeys.systems(novelId),
          predicate: (q) => Array.isArray(q.state.data),
        },
        (old) => {
          if (!Array.isArray(old)) return old
          return old.map((s) => (s.id === systemId ? applySystemPatch(s, data) : s))
        },
      )

      return { previousSystem, previousSystemLists: previousSystemLists as Array<[QueryKey, WorldSystem[] | undefined]> }
    },
    onError: (_err, vars, context) => {
      if (context?.previousSystem) {
        qc.setQueryData(worldKeys.system(novelId, vars.systemId), context.previousSystem)
      }
      context?.previousSystemLists?.forEach(([key, data]) => {
        qc.setQueryData(key, data)
      })
      toast(LABELS.ERROR_SAVE_FAILED)
    },
    onSuccess: (updated, { systemId }) => {
      qc.setQueryData<WorldSystem>(worldKeys.system(novelId, systemId), updated)
      qc.setQueriesData<WorldSystem[]>(
        {
          queryKey: worldKeys.systems(novelId),
          predicate: (q) => Array.isArray(q.state.data),
        },
        (old) => {
          if (!Array.isArray(old)) return old
          return old.map((s) => (s.id === systemId ? { ...s, ...updated } : s))
        },
      )
    },
  })
}

export function useDeleteSystem(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (systemId: number) => worldApi.deleteSystem(novelId, systemId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) }) },
    onError: () => toast(LABELS.ERROR_DELETE_FAILED),
  })
}

export function useConfirmSystems(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.confirmSystems(novelId, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) }) },
    onError: () => toast(LABELS.ERROR_CONFIRM_FAILED),
  })
}

export function useRejectSystems(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.rejectSystems(novelId, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.systems(novelId) }) },
    onError: () => toast(LABELS.ERROR_REJECT_FAILED),
  })
}
