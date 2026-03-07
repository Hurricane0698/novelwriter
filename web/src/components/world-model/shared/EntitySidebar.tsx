import { useEffect, useState, useMemo, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { WorldBuildSection } from '@/components/world-model/shared/WorldBuildSection'
import { useWorldEntities, useCreateEntity, useConfirmEntities, useRejectEntities } from '@/hooks/world/useEntities'
import { LABELS } from '@/constants/labels'
import type { WorldEntity } from '@/types/api'

export function EntitySidebar({ novelId, selectedEntityId, onSelectEntity, bottomSlot }: {
  novelId: number
  selectedEntityId: number | null
  onSelectEntity: (id: number) => void
  bottomSlot?: React.ReactNode
}) {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set())
  const { data: entities = [], isLoading } = useWorldEntities(novelId)
  const createEntity = useCreateEntity(novelId)
  const confirmEntities = useConfirmEntities(novelId)
  const rejectEntities = useRejectEntities(novelId)

  const handleConfirmOne = (id: number) => confirmEntities.mutate([id])
  const handleRejectOne = (id: number) => rejectEntities.mutate([id])

  const entityTypes = useMemo(
    () => [...new Set(entities.map(e => e.entity_type))],
    [entities]
  )

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    const list = entities.filter(e => {
      if (typeFilter.size > 0 && !typeFilter.has(e.entity_type)) return false
      if (!q) return true
      return e.name.toLowerCase().includes(q) || e.aliases.some(a => a.toLowerCase().includes(q))
    })
    // Draft-first sorting: drafts first (newest at top), then confirmed by name
    return list.sort((a, b) => {
      if (a.status === 'draft' && b.status !== 'draft') return -1
      if (a.status !== 'draft' && b.status === 'draft') return 1
      if (a.status === 'draft' && b.status === 'draft') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      }
      return a.name.localeCompare(b.name)
    })
  }, [entities, search, typeFilter])

  const draftIds = useMemo(() => filtered.filter(e => e.status === 'draft').map(e => e.id), [filtered])

  useEffect(() => {
    if (selectedEntityId === null) return
    const el = document.getElementById(`entity-${selectedEntityId}`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selectedEntityId, entities])

  const toggleType = (t: string) => {
    setTypeFilter(prev => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t); else next.add(t)
      return next
    })
  }

  const handleCreate = () => {
    createEntity.mutate({ name: '新实体', entity_type: 'Character' })
  }

  const handleConfirmAll = () => {
    if (draftIds.length > 0) confirmEntities.mutate(draftIds)
  }

  return (
    <div
      className="shrink-0 flex flex-col min-h-0 h-full w-[280px] border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl"
      data-testid="entity-sidebar"
    >
      <div className="p-4 space-y-2">
        <Input
          placeholder={LABELS.ENTITY_SEARCH_PLACEHOLDER}
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="h-9 text-sm bg-transparent border-[var(--nw-glass-border)] placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="entity-search"
        />
        {entityTypes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {entityTypes.map(t => (
              <button
                key={t}
                onClick={() => toggleType(t)}
                className={cn(
                  'rounded-full px-2 py-0.5 text-xs border transition-colors',
                  typeFilter.has(t)
                    ? 'bg-[var(--nw-glass-bg-hover)] text-foreground border-[var(--nw-glass-border-hover)]'
                    : 'border-[var(--nw-glass-border)] text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)]'
                )}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        {draftIds.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="w-full h-8 text-xs border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)]"
            onClick={handleConfirmAll}
            disabled={confirmEntities.isPending}
          >
            {LABELS.CONFIRM_ALL_ENTITIES} ({draftIds.length})
          </Button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-1 p-2">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="h-9 rounded bg-muted animate-pulse" />
            ))}
          </div>
        ) : filtered.map(e => (
          <EntityRow
            key={e.id}
            entity={e}
            selected={e.id === selectedEntityId}
            onClick={() => onSelectEntity(e.id)}
            onConfirm={e.status === 'draft' ? () => handleConfirmOne(e.id) : undefined}
            onReject={e.status === 'draft' ? () => handleRejectOne(e.id) : undefined}
          />
        ))}
      </div>
      <div className="p-4 border-t border-[var(--nw-glass-border)] space-y-3">
        {bottomSlot ? <div className="space-y-3">{bottomSlot}</div> : null}
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)]"
          onClick={handleCreate}
          data-testid="entity-create"
        >
          {LABELS.ENTITY_NEW}
        </Button>
        <WorldBuildSection novelId={novelId} />
      </div>
    </div>
  )
}

function EntityRow({ entity, selected, onClick, onConfirm, onReject }: {
  entity: WorldEntity
  selected: boolean
  onClick: () => void
  onConfirm?: () => void
  onReject?: () => void
}) {
  const isDraft = entity.status === 'draft'

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onClick()
    }
  }

  return (
    <div
      id={`entity-${entity.id}`}
      className={cn(
        'group w-full text-left px-4 py-2 text-sm flex items-center gap-2 transition-colors cursor-pointer',
        selected ? 'bg-[var(--nw-glass-bg-hover)] border-l-2 border-l-accent' : 'hover:bg-[var(--nw-glass-bg-hover)]'
      )}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      data-testid={`entity-row-${entity.id}`}
    >
      {isDraft && (
        <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--color-status-draft))] shrink-0" />
      )}
      <span className="truncate flex-1 text-foreground">{entity.name}</span>
      {isDraft && (onConfirm || onReject) ? (
        <span className="hidden group-hover:flex group-focus-within:flex items-center gap-0.5 shrink-0">
          {onConfirm && (
            <button
              onClick={(e) => { e.stopPropagation(); onConfirm() }}
              className="rounded p-0.5 text-muted-foreground hover:text-[hsl(var(--color-status-confirmed))] hover:bg-[hsl(var(--color-status-confirmed)/0.10)] transition-colors"
              title="确认"
              data-testid={`entity-confirm-${entity.id}`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </button>
          )}
          {onReject && (
            <button
              onClick={(e) => { e.stopPropagation(); onReject() }}
              className="rounded p-0.5 text-muted-foreground hover:text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)] transition-colors"
              title="拒绝"
              data-testid={`entity-reject-${entity.id}`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </span>
      ) : (
        <span className="text-xs text-muted-foreground shrink-0">{entity.entity_type}</span>
      )}
    </div>
  )
}
