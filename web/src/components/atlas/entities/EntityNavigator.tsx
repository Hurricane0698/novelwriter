import { useOverlayPanelFocus } from '@/hooks/useOverlayPanelFocus'
import { useEffect, useState, useMemo, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'
import { PanelResizeHandle } from '@/components/novel-shell/PanelResizeHandle'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useWorldEntities, useCreateEntity, useConfirmEntities, useRejectEntities } from '@/hooks/world/useEntities'
import { LABELS } from '@/constants/labels'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { WorldEntity } from '@/types/api'

export function EntityNavigator({ novelId, selectedEntityId, onSelectEntity, bottomSlot, width = 280, onResize, onClose, hidden = false, overlay = false }: {
  width?: number
  onResize?: (width: number) => void
  onClose?: () => void
  hidden?: boolean
  overlay?: boolean
  novelId: number
  selectedEntityId: number | null
  onSelectEntity: (id: number) => void
  bottomSlot?: React.ReactNode
}) {
  const { locale, t } = useUiLocale()
  const panelRef = useOverlayPanelFocus(overlay && !hidden)
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
    createEntity.mutate({ name: t('worldModel.entity.defaultName'), entity_type: 'Character' })
  }

  const handleConfirmAll = () => {
    if (draftIds.length > 0) confirmEntities.mutate(draftIds)
  }

  return (
    <div
      className={cn('relative shrink-0 flex-col min-h-0 h-full border-r border-border/50 bg-background', hidden ? 'hidden' : 'flex', overlay && '!absolute left-0 top-12 bottom-0 !h-auto z-30 shadow-xl')}
      style={{ width }} hidden={hidden}
      ref={panelRef} tabIndex={-1} aria-label={t('worldModel.graph.toggleNavigator')}
      onKeyDown={event => { if (overlay && event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); onClose?.() } }}
      data-testid="entity-navigator"
    >
      {onResize && <PanelResizeHandle side="right" width={width} min={200} max={400} onResize={onResize} label={t('worldModel.graph.resizeNavigator')} />}
      {onClose && <header className="flex h-10 shrink-0 items-center justify-between px-4 pt-2">
        <span className="text-xs text-muted-foreground">{t('worldModel.common.entities')}</span>
        <button type="button" onClick={onClose} aria-label={t('worldModel.graph.closeNavigator')} className="rounded p-1.5 text-muted-foreground hover:bg-foreground/5"><X size={14} /></button>
      </header>}
      <div className="shrink-0 p-4 space-y-2">
        <Input
          placeholder={t('worldModel.common.searchEntities')}
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
            className="w-full h-8 text-xs border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground"
            onClick={handleConfirmAll}
            disabled={confirmEntities.isPending}
          >
            {t('dialog.confirm')} {t('worldModel.common.all')} ({draftIds.length})
          </Button>
        )}
      </div>
      <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
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
            locale={locale}
            selected={e.id === selectedEntityId}
            onClick={() => onSelectEntity(e.id)}
            onConfirm={e.status === 'draft' ? () => handleConfirmOne(e.id) : undefined}
            onReject={e.status === 'draft' ? () => handleRejectOne(e.id) : undefined}
          />
        ))}
      </div>
      <div className="shrink-0 p-3 border-t border-[var(--nw-glass-border)] space-y-2">
        {bottomSlot ? <div className="space-y-2">{bottomSlot}</div> : null}
        <button
          type="button"
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={handleCreate}
          data-testid="entity-create"
        >
          {t('worldModel.entity.new')}
        </button>
      </div>
    </div>
  )
}

function EntityRow({ entity, locale, selected, onClick, onConfirm, onReject }: {
  entity: WorldEntity
  locale: 'zh' | 'en'
  selected: boolean
  onClick: () => void
  onConfirm?: () => void
  onReject?: () => void
}) {
  const { t } = useUiLocale()
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
        'group w-full scroll-mb-64 text-left px-4 py-2 text-sm flex items-center gap-2 transition-colors cursor-pointer',
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
              title={t('dialog.confirm')}
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
              title={t('worldModel.common.reject')}
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
        <span className="text-xs text-muted-foreground shrink-0">{LABELS.ENTITY_TYPE_LABEL(entity.entity_type, locale)}</span>
      )}
    </div>
  )
}
