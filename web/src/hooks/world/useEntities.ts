import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { worldApi } from '@/services/api'
import { worldKeys } from './keys'
import { useToast } from '@/components/world-model/shared/useToast'
import { LABELS } from '@/constants/labels'
import type { CreateEntityRequest, UpdateEntityRequest, CreateAttributeRequest, UpdateAttributeRequest, WorldEntity, WorldEntityDetail } from '@/types/api'

function applyEntityPatch<T extends { name: string; entity_type: string; description: string; aliases: string[] }>(
  prev: T,
  patch: UpdateEntityRequest,
): T {
  const next = { ...prev }
  if (patch.name !== undefined) next.name = patch.name
  if (patch.entity_type !== undefined) next.entity_type = patch.entity_type
  if (patch.description !== undefined) next.description = patch.description
  if (patch.aliases !== undefined) next.aliases = patch.aliases
  return next
}

export function useWorldEntities(novelId: number, params?: { entity_type?: string; status?: string }) {
  return useQuery({
    queryKey: [...worldKeys.entities(novelId), params],
    queryFn: () => worldApi.listEntities(novelId, params),
    enabled: Number.isFinite(novelId) && novelId > 0,
  })
}

export function useWorldEntity(novelId: number, entityId: number | null) {
  return useQuery({
    queryKey: worldKeys.entity(novelId, entityId!),
    queryFn: () => worldApi.getEntity(novelId, entityId!),
    enabled: entityId !== null,
  })
}

export function useCreateEntity(novelId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateEntityRequest) => worldApi.createEntity(novelId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) }) },
  })
}

export function useUpdateEntity(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: ({ entityId, data }: { entityId: number; data: UpdateEntityRequest }) =>
      worldApi.updateEntity(novelId, entityId, data),
    onMutate: async ({ entityId, data }) => {
      await qc.cancelQueries({ queryKey: worldKeys.entity(novelId, entityId) })
      await qc.cancelQueries({ queryKey: worldKeys.entities(novelId) })

      const previousEntity = qc.getQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId))
      // NOTE: worldKeys.entities(...) is a prefix for both list and detail keys:
      // - list:   ['world', novelId, 'entities', params]
      // - detail: ['world', novelId, 'entities', entityId]
      // Guard with `predicate` so we only snapshot list queries here.
      const previousEntityLists = qc.getQueriesData<WorldEntity[]>({
        queryKey: worldKeys.entities(novelId),
        predicate: (q) => Array.isArray(q.state.data),
      })

      if (previousEntity) {
        qc.setQueryData<WorldEntityDetail>(
          worldKeys.entity(novelId, entityId),
          applyEntityPatch(previousEntity, data),
        )
      }

      qc.setQueriesData<WorldEntity[]>(
        {
          queryKey: worldKeys.entities(novelId),
          predicate: (q) => Array.isArray(q.state.data),
        },
        (old) => {
          if (!Array.isArray(old)) return old
          return old.map((e) => (e.id === entityId ? applyEntityPatch(e, data) : e))
        },
      )

      return { previousEntity, previousEntityLists: previousEntityLists as Array<[QueryKey, WorldEntity[] | undefined]> }
    },
    onError: (_err, vars, context) => {
      if (context?.previousEntity) {
        qc.setQueryData(worldKeys.entity(novelId, vars.entityId), context.previousEntity)
      }
      context?.previousEntityLists?.forEach(([key, data]) => {
        qc.setQueryData(key, data)
      })
      toast(LABELS.ERROR_SAVE_FAILED)
    },
    onSuccess: (updated, { entityId }) => {
      const current = qc.getQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId))
      if (current) {
        qc.setQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId), { ...current, ...updated })
      }
      qc.setQueriesData<WorldEntity[]>(
        {
          queryKey: worldKeys.entities(novelId),
          predicate: (q) => Array.isArray(q.state.data),
        },
        (old) => {
          if (!Array.isArray(old)) return old
          return old.map((e) => (e.id === entityId ? { ...e, ...updated } : e))
        },
      )
    },
  })
}

export function useDeleteEntity(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (entityId: number) => worldApi.deleteEntity(novelId, entityId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
      qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
    },
    onError: () => toast(LABELS.ERROR_DELETE_FAILED),
  })
}

export function useConfirmEntities(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.confirmEntities(novelId, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) }) },
    onError: () => toast(LABELS.ERROR_CONFIRM_FAILED),
  })
}

export function useRejectEntities(novelId: number) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: (ids: number[]) => worldApi.rejectEntities(novelId, ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
      qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
    },
    onError: () => toast(LABELS.ERROR_REJECT_FAILED),
  })
}

export function useCreateAttribute(novelId: number, entityId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAttributeRequest) => worldApi.createAttribute(novelId, entityId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.entity(novelId, entityId) }) },
  })
}

export function useUpdateAttribute(novelId: number, entityId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ attrId, data }: { attrId: number; data: UpdateAttributeRequest }) =>
      worldApi.updateAttribute(novelId, entityId, attrId, data),
    onMutate: async ({ attrId, data }) => {
      await qc.cancelQueries({ queryKey: worldKeys.entity(novelId, entityId) })
      const previous = qc.getQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId))

      if (previous) {
        qc.setQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId), {
          ...previous,
          attributes: previous.attributes.map(attr =>
            attr.id === attrId ? { ...attr, ...data } : attr
          )
        })
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        qc.setQueryData(worldKeys.entity(novelId, entityId), context.previous)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: worldKeys.entity(novelId, entityId) })
    },
  })
}

export function useDeleteAttribute(novelId: number, entityId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (attrId: number) => worldApi.deleteAttribute(novelId, entityId, attrId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: worldKeys.entity(novelId, entityId) }) },
  })
}

export function useReorderAttributes(novelId: number, entityId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (order: number[]) => worldApi.reorderAttributes(novelId, entityId, order),
    onMutate: async (order) => {
      await qc.cancelQueries({ queryKey: worldKeys.entity(novelId, entityId) })
      const previous = qc.getQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId))

      if (previous) {
        // Create a map for quick access
        const attrMap = new Map(previous.attributes.map(a => [a.id, a]))
        // Reconstruct attributes array based on new order
        const newAttributes = order
          .map(id => attrMap.get(id))
          .filter((a): a is NonNullable<typeof a> => !!a)

        // Append any attributes that might be missing from the order (though unlikely in valid usage)
        const orderedIds = new Set(order)
        previous.attributes.forEach(a => {
          if (!orderedIds.has(a.id)) newAttributes.push(a)
        })

        qc.setQueryData<WorldEntityDetail>(worldKeys.entity(novelId, entityId), {
          ...previous,
          attributes: newAttributes
        })
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        qc.setQueryData(worldKeys.entity(novelId, entityId), context.previous)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: worldKeys.entity(novelId, entityId) })
    },
  })
}
