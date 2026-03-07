import { useState } from 'react'
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { AttributeRow } from '@/components/world-model/entities/AttributeRow'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { GlassSurface } from '@/components/ui/glass-surface'
import { useWorldEntity, useUpdateEntity, useDeleteEntity, useCreateAttribute, useReorderAttributes } from '@/hooks/world/useEntities'
import { LABELS } from '@/constants/labels'
import type { WorldEntityAttribute } from '@/types/api'

function SortableAttributeRow({ novelId, entityId, attribute }: {
  novelId: number
  entityId: number
  attribute: WorldEntityAttribute
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: attribute.id })
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} {...attributes}>
      <AttributeRow novelId={novelId} entityId={entityId} attribute={attribute} dragListeners={listeners} />
    </div>
  )
}

const COMMON_TYPES = ['Character', 'Location', 'Faction', 'Concept', 'Vehicle', 'Item']

export function EntityDetail({ novelId, entityId, onDeleted }: {
  novelId: number
  entityId: number | null
  onDeleted?: () => void
}) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showTypeDropdown, setShowTypeDropdown] = useState(false)
  const [customType, setCustomType] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [newAlias, setNewAlias] = useState('')

  const { data: entity } = useWorldEntity(novelId, entityId)
  const updateEntity = useUpdateEntity(novelId)
  const deleteEntity = useDeleteEntity(novelId)
  const createAttr = useCreateAttribute(novelId, entityId ?? 0)
  const reorderAttrs = useReorderAttributes(novelId, entityId ?? 0)

  if (!entityId || !entity) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        {LABELS.ENTITY_EMPTY}
      </div>
    )
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const ids = entity.attributes.map(a => a.id)
    const oldIdx = ids.indexOf(active.id as number)
    const newIdx = ids.indexOf(over.id as number)
    const newOrder = [...ids]
    newOrder.splice(oldIdx, 1)
    newOrder.splice(newIdx, 0, active.id as number)
    reorderAttrs.mutate(newOrder)
  }

  const handleDelete = () => {
    deleteEntity.mutate(entityId, { onSuccess: () => onDeleted?.() })
    setShowDeleteConfirm(false)
  }

  const handleTypeSelect = (type: string) => {
    updateEntity.mutate({ entityId, data: { entity_type: type } })
    setShowTypeDropdown(false)
    setCustomType('')
  }

  const isDraft = entity.status === 'draft'
  const statusVarName = isDraft ? '--color-status-draft' : '--color-status-confirmed'
  const statusDot = {
    background: [
      'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.55), rgba(255,255,255,0) 55%)',
      `radial-gradient(circle at 60% 70%, hsl(var(${statusVarName}) / 0.65), hsl(var(${statusVarName}) / 0.18) 70%)`,
    ].join(', '),
    boxShadow: `0 0 12px hsl(var(${statusVarName}) / 0.55)`,
  } as const

  const aliases = entity.aliases ?? []

  const handleAddAlias = () => {
    const value = newAlias.trim()
    if (!value) return
    if (aliases.some((a) => a.trim() === value)) {
      setNewAlias('')
      return
    }
    updateEntity.mutate({ entityId, data: { aliases: [...aliases, value] } })
    setNewAlias('')
  }

  const handleRemoveAlias = (alias: string) => {
    updateEntity.mutate({ entityId, data: { aliases: aliases.filter((a) => a !== alias) } })
  }

  return (
    <div className="flex-1 overflow-y-auto" data-testid="entity-detail">
      <div className="max-w-5xl mx-auto px-8 py-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full" style={statusDot} aria-label={entity.status} title={entity.status} />
              <InlineEdit
                value={entity.name}
                onSave={v => updateEntity.mutate({ entityId, data: { name: v } })}
                className="text-2xl font-light text-foreground"
              />
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <button
                  className="text-xs px-2 py-0.5 rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
                  onClick={() => setShowTypeDropdown(!showTypeDropdown)}
                >
                  {entity.entity_type}
                </button>
                {showTypeDropdown && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowTypeDropdown(false)} />
                    <GlassSurface
                      variant="floating"
                      className="absolute top-full left-0 mt-1 z-20 rounded-xl py-1 min-w-[160px]"
                    >
                      {COMMON_TYPES.map(t => (
                        <button key={t} className="block w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--nw-glass-bg-hover)]" onClick={() => handleTypeSelect(t)}>
                          {t}
                        </button>
                      ))}
                      <div className="h-px bg-[var(--nw-glass-border)] mx-3 my-1" />
                      <div className="px-3 py-1">
                        <input
                          className="w-full text-sm rounded-lg border border-[var(--nw-glass-border)] bg-transparent px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          placeholder="Custom..."
                          value={customType}
                          onChange={e => setCustomType(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter' && customType.trim()) handleTypeSelect(customType.trim()) }}
                        />
                      </div>
                    </GlassSurface>
                  </>
                )}
              </div>
              <span className={cn('text-xs', entity.status === 'confirmed' ? 'text-[hsl(var(--color-status-confirmed))]' : 'text-[hsl(var(--color-status-draft))]')}>
                {entity.status === 'confirmed' ? '✓' : '●'} {entity.status}
              </span>
            </div>
          </div>
          {/* Menu */}
          <div className="relative">
            <button className="text-muted-foreground hover:text-foreground px-2 py-1" onClick={() => setShowMenu(!showMenu)}>···</button>
            {showMenu && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
                <GlassSurface
                  variant="floating"
                  className="absolute right-0 top-full mt-1 z-20 rounded-xl py-1 min-w-[140px]"
                >
                  <button
                    className="block w-full text-left px-3 py-2 text-sm text-[hsl(var(--color-danger))] hover:bg-[var(--nw-glass-bg-hover)]"
                    onClick={() => { setShowMenu(false); setShowDeleteConfirm(true) }}
                    data-testid="entity-delete-menu"
                  >
                    {LABELS.ENTITY_DELETE}
                  </button>
                </GlassSurface>
              </>
            )}
          </div>
        </div>

        {/* Description */}
        <div className="mt-4">
          <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-4">
            <div className="text-xs font-semibold tracking-wider text-muted-foreground mb-2">描述</div>
            <InlineEdit
              value={entity.description}
              onSave={v => updateEntity.mutate({ entityId, data: { description: v } })}
              multiline
              variant="transparent"
              className="text-sm text-foreground"
              placeholder={LABELS.PH_DESCRIPTION}
            />
          </div>
        </div>

        {/* Aliases */}
        <div className="mt-4">
          <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-4">
            <div className="text-xs font-semibold tracking-wider text-muted-foreground mb-2">别名</div>
            <div className="flex flex-wrap items-center gap-2">
              {aliases.length === 0 ? (
                <span className="text-sm text-muted-foreground">（暂无别名）</span>
              ) : aliases.map((alias) => (
                <span
                  key={alias}
                  className="group inline-flex items-center gap-1 rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-2.5 py-1 text-xs text-muted-foreground"
                >
                  {alias}
                  <button
                    type="button"
                    className="ml-0.5 text-muted-foreground/70 opacity-0 group-hover:opacity-100 transition-opacity hover:text-[hsl(var(--color-danger))]"
                    onClick={() => handleRemoveAlias(alias)}
                    aria-label={`Remove alias ${alias}`}
                    title="移除"
                  >
                    ×
                  </button>
                </span>
              ))}

              <div className="flex items-center gap-2">
                <input
                  className="h-7 w-40 rounded-full border border-[var(--nw-glass-border)] bg-transparent px-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  value={newAlias}
                  placeholder="添加别名..."
                  onChange={(e) => setNewAlias(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleAddAlias() }}
                />
                <button
                  type="button"
                  className="h-7 rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-3 text-xs text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors disabled:opacity-50"
                  onClick={handleAddAlias}
                  disabled={!newAlias.trim()}
                >
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Attributes */}
        <div className="mt-8">
          <div className="flex items-end justify-between gap-4 mb-3">
            <h3 className="text-sm font-medium text-muted-foreground">
              {LABELS.ENTITY_ATTRIBUTES} ({entity.attributes.length})
            </h3>
            <button
              type="button"
              className="text-xs rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-3 py-1 text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
              data-testid="add-attribute"
              onClick={() => createAttr.mutate({ key: '', surface: '' })}
            >
              {LABELS.ENTITY_ADD_ATTRIBUTE}
            </button>
          </div>

          <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden">
            <div className="grid grid-cols-[16px_120px_1fr_1fr_44px_24px] items-center px-4 py-2 text-[11px] font-semibold text-muted-foreground border-b border-[var(--nw-glass-border)]">
              <div />
              <div>属性名</div>
              <div>表层</div>
              <div>真相</div>
              <div className="text-center">可见</div>
              <div />
            </div>
            <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={entity.attributes.map(a => a.id)} strategy={verticalListSortingStrategy}>
                {entity.attributes.map(attr => (
                  <SortableAttributeRow
                    key={attr.id}
                    novelId={novelId}
                    entityId={entityId}
                    attribute={attr}
                  />
                ))}
              </SortableContext>
            </DndContext>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={showDeleteConfirm}
        title={LABELS.ENTITY_DELETE}
        description={LABELS.ENTITY_DELETE_CONFIRM}
        tone="destructive"
        onConfirm={handleDelete}
        onClose={() => setShowDeleteConfirm(false)}
      />
    </div>
  )
}
