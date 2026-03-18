import { useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { LABELS } from '@/constants/labels'
import { useWorldRelationships, useCreateRelationship, useUpdateRelationship, useDeleteRelationship, useConfirmRelationships } from '@/hooks/world/useRelationships'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { StarGraph } from './StarGraph'
import { RelationshipInspector } from './RelationshipInspector'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BottomSheet } from '@/components/world-model/shared/BottomSheet'
import type { UpdateRelationshipRequest, WorldEntity, WorldRelationship } from '@/types/api'

function RelationshipsGraphSection({
  centerId,
  relationships,
  entities,
  onSelectEntity,
  onUpdate,
  onConfirm,
  onDelete,
  selectedRelationshipId,
}: {
  centerId: number
  relationships: WorldRelationship[]
  entities: WorldEntity[]
  onSelectEntity: (id: number) => void
  onUpdate: (relId: number, data: UpdateRelationshipRequest) => void
  onConfirm: (relId: number) => void
  onDelete: (relId: number) => void
  selectedRelationshipId?: number | null
}) {
  const [selectedRelIdState, setSelectedRelId] = useState<number | null>(() => selectedRelationshipId ?? null)

  const selectedRelId = selectedRelIdState !== null
    && relationships.some((relationship) => relationship.id === selectedRelIdState)
    ? selectedRelIdState
    : null

  const effectiveSelectedRel = selectedRelId
    ? (relationships.find((r) => r.id === selectedRelId) ?? null)
    : null

  return (
    <>
      <div className="flex-1 min-h-0">
        <StarGraph
          centerId={centerId}
          relationships={relationships}
          entities={entities}
          onSelectEntity={onSelectEntity}
          onSelectEdge={(rel) => setSelectedRelId(rel.id)}
          selectedRelId={selectedRelId}
          onClearSelection={() => setSelectedRelId(null)}
        />
      </div>
      <RelationshipInspector
        key={effectiveSelectedRel?.id ?? 'none'}
        rel={effectiveSelectedRel}
        entities={entities}
        onUpdate={onUpdate}
        onConfirm={onConfirm}
        onDelete={onDelete}
      />
    </>
  )
}

export function RelationshipsTab({
  novelId,
  selectedEntityId,
  onSelectEntity,
  selectedRelationshipId,
  creating: creatingProp,
  onCreatingChange,
}: {
  novelId: number
  selectedEntityId: number | null
  onSelectEntity: (id: number) => void
  selectedRelationshipId?: number | null
  creating?: boolean
  onCreatingChange?: (open: boolean) => void
}) {
  const { data: relationships = [] } = useWorldRelationships(
    novelId,
    selectedEntityId !== null ? { entity_id: selectedEntityId } : undefined,
    selectedEntityId !== null,
  )
  const { data: entities = [] } = useWorldEntities(novelId)
  const createRel = useCreateRelationship(novelId)
  const updateRel = useUpdateRelationship(novelId)
  const deleteRel = useDeleteRelationship(novelId)
  const confirmRels = useConfirmRelationships(novelId)

  const [creatingInternal, setCreatingInternal] = useState(false)
  const creatingControlled = typeof creatingProp === 'boolean' && typeof onCreatingChange === 'function'
  const creating = creatingControlled ? creatingProp : creatingInternal
  const setCreating = creatingControlled ? onCreatingChange : setCreatingInternal
  const [newTargetId, setNewTargetId] = useState<number | ''>('')
  const [newLabel, setNewLabel] = useState('')
  const [targetSearch, setTargetSearch] = useState('')
  const targetSearchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!creating) return
    // BottomSheet keeps children mounted; focus manually on open.
    requestAnimationFrame(() => targetSearchRef.current?.focus())
  }, [creating])

  const filteredTargets = useMemo(() => {
    const q = targetSearch.trim().toLowerCase()
    return entities
      .filter((e) => e.id !== selectedEntityId)
      .filter((e) => {
        if (!q) return true
        return (
          e.name.toLowerCase().includes(q) ||
          (e.description ?? '').toLowerCase().includes(q) ||
          e.aliases?.some((a) => a.toLowerCase().includes(q))
        )
      })
  }, [entities, selectedEntityId, targetSearch])

  const sourceName = useMemo(
    () => entities.find((e) => e.id === selectedEntityId)?.name,
    [entities, selectedEntityId],
  )

  const selectedTarget = useMemo(() => {
    if (!newTargetId) return null
    return entities.find((e) => e.id === Number(newTargetId)) ?? null
  }, [entities, newTargetId])

  const handleUpdate = (relId: number, data: UpdateRelationshipRequest) => {
    updateRel.mutate({ relId, data })
  }

  const handleConfirm = (relId: number) => {
    confirmRels.mutate([relId])
  }

  const handleDelete = (relId: number) => {
    deleteRel.mutate(relId)
  }

  const handleCreate = () => {
    if (selectedEntityId === null || newTargetId === '' || !newLabel) return
    createRel.mutate(
      { source_id: selectedEntityId, target_id: Number(newTargetId), label: newLabel },
      { onSuccess: () => { setCreating(false); setNewTargetId(''); setNewLabel('') } },
    )
  }

  if (selectedEntityId === null) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        {LABELS.REL_EMPTY}
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 overflow-hidden">
      <div className="flex-1 min-h-0 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden flex flex-col">
        <RelationshipsGraphSection
          key={`${selectedEntityId}:${selectedRelationshipId ?? 'none'}`}
          centerId={selectedEntityId}
          relationships={relationships}
          entities={entities}
          onSelectEntity={onSelectEntity}
          onUpdate={handleUpdate}
          onConfirm={handleConfirm}
          onDelete={handleDelete}
          selectedRelationshipId={selectedRelationshipId}
        />
      </div>
      <BottomSheet open={creating} onClose={() => setCreating(false)}>
        <div className="space-y-3">
          <div className="space-y-0.5">
            <h3 className="font-semibold">{LABELS.REL_NEW}</h3>
            <div className="text-xs text-muted-foreground">
              从 <span className="text-foreground">{sourceName ?? selectedEntityId}</span>{' '}
              到 <span className="text-foreground">{selectedTarget?.name ?? '（请选择目标实体）'}</span>
            </div>
          </div>
          <div className="space-y-2">
            <Input
              ref={targetSearchRef}
              placeholder="搜索目标实体..."
              value={targetSearch}
              onChange={(e) => setTargetSearch(e.target.value)}
              className="h-9 text-sm bg-transparent border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
            />

            <div className="max-h-64 overflow-y-auto rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-1">
              {filteredTargets.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  className={cn(
                    'w-full text-left rounded-lg px-3 py-2 text-sm transition-colors',
                    newTargetId === e.id
                      ? 'bg-[var(--nw-glass-bg-hover)] border border-[var(--nw-glass-border-hover)]'
                      : 'border border-transparent hover:bg-[var(--nw-glass-bg-hover)]',
                  )}
                  onClick={() => setNewTargetId(e.id)}
                >
                  <div className="flex items-center gap-2">
                    <div className="font-medium text-foreground truncate flex-1">{e.name}</div>
                    <div className="text-xs text-muted-foreground shrink-0">{e.entity_type}</div>
                    {newTargetId === e.id ? (
                      <div className="text-xs text-[hsl(var(--color-accent))] shrink-0">✓</div>
                    ) : null}
                  </div>
                  {e.description ? (
                    <div className="text-xs text-muted-foreground line-clamp-1">{e.description}</div>
                  ) : null}
                </button>
              ))}
              {filteredTargets.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">没有匹配的目标实体</div>
              ) : null}
            </div>
          </div>
          <input
            className="w-full rounded border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0"
            placeholder="关系标签"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setCreating(false)}>{LABELS.CANCEL}</Button>
            <Button size="sm" onClick={handleCreate} disabled={!newTargetId || !newLabel}>{LABELS.CONFIRM}</Button>
          </div>
        </div>
      </BottomSheet>
    </div>
  )
}
