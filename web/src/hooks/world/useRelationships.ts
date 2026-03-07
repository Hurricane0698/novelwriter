import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { worldApi } from '@/services/api'
import { worldKeys } from './keys'
import { useToast } from '@/components/world-model/shared/useToast'
import { LABELS } from '@/constants/labels'
import type { CreateRelationshipRequest, UpdateRelationshipRequest, WorldRelationship } from '@/types/api'

function applyRelationshipPatch(prev: WorldRelationship, patch: UpdateRelationshipRequest): WorldRelationship {
  const next = { ...prev }
  if (patch.label !== undefined) next.label = patch.label
  if (patch.description !== undefined) next.description = patch.description
  if (patch.visibility !== undefined) next.visibility = patch.visibility
  return next
}

export function useWorldRelationships(
  novelId: number,
  params?: {
    q?: string
    entity_id?: number
    source_id?: number
    target_id?: number
    origin?: string
    worldpack_pack_id?: string
    visibility?: string
    status?: string
  },
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: [...worldKeys.relationships(novelId), params],
    queryFn: () => worldApi.listRelationships(novelId, params),
    enabled: enabled && Number.isFinite(novelId) && novelId > 0,
  })
}

export function useCreateRelationship(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateRelationshipRequest) => worldApi.createRelationship(novelId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) }) },
  })
}

export function useUpdateRelationship(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: ({ relId, data }: { relId: number; data: UpdateRelationshipRequest }) =>
      worldApi.updateRelationship(novelId, relId, data),
    onMutate: async ({ relId, data }) => {
      await qc.cancelQueries({ queryKey: worldKeys.relationships(novelId) })
      const previousRelationshipLists = qc.getQueriesData<WorldRelationship[]>({ queryKey: worldKeys.relationships(novelId) })

      qc.setQueriesData<WorldRelationship[]>(
        { queryKey: worldKeys.relationships(novelId) },
        (old) => {
          if (!old) return old
          return old.map((r) => (r.id === relId ? applyRelationshipPatch(r, data) : r))
        },
      )

      return { previousRelationshipLists: previousRelationshipLists as Array<[QueryKey, WorldRelationship[] | undefined]> }
    },
    onError: (_err, _vars, context) => {
      context?.previousRelationshipLists?.forEach(([key, data]) => {
        qc.setQueryData(key, data)
      })
      toast(LABELS.ERROR_SAVE_FAILED)
    },
    onSuccess: (updated, { relId }) => {
      qc.setQueriesData<WorldRelationship[]>(
        { queryKey: worldKeys.relationships(novelId) },
        (old) => {
          if (!old) return old
          return old.map((r) => (r.id === relId ? { ...r, ...updated } : r))
        },
      )
    },
  })
}

export function useDeleteRelationship(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (relId: number) => worldApi.deleteRelationship(novelId, relId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) }) },
    onError: () => toast(LABELS.ERROR_DELETE_FAILED),
  })
}

export function useConfirmRelationships(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.confirmRelationships(novelId, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) }) },
    onError: () => toast(LABELS.ERROR_CONFIRM_FAILED),
  })
}

export function useRejectRelationships(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.rejectRelationships(novelId, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) }) },
    onError: () => toast(LABELS.ERROR_REJECT_FAILED),
  })
}
