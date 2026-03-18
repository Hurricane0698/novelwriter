import { useEffect, useMemo, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { DraftReviewSummaryCard, type DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Input } from '@/components/ui/input'
import { GlassSurface } from '@/components/ui/glass-surface'
import { WorldBuildPanel } from '@/components/world-model/shared/WorldBuildPanel'
import { useWorldSystems, useCreateSystem, useUpdateSystem, useDeleteSystem, useConfirmSystems, useRejectSystems } from '@/hooks/world/useSystems'
import { LABELS } from '@/constants/labels'
import { getSystemDisplayTypeLabel } from '@/lib/worldSystemDisplay'
import type { WorldSystem, SystemDisplayType } from '@/types/api'

const DISPLAY_TYPES: SystemDisplayType[] = ['hierarchy', 'timeline', 'list']

const INITIAL_DATA: Record<SystemDisplayType, Record<string, unknown>> = {
  hierarchy: { nodes: [] },
  timeline: { events: [] },
  list: { items: [] },
}

export function SystemNavigator({ novelId, selectedId, onSelect, onOpenDraftReview }: {
  novelId: number
  selectedId: number | null
  onSelect: (system: WorldSystem) => void
  onOpenDraftReview: (kind?: DraftReviewKind) => void
}) {
  const { data: systems } = useWorldSystems(novelId)
  const createSystem = useCreateSystem(novelId)
  const updateSystem = useUpdateSystem(novelId)
  const deleteSystem = useDeleteSystem(novelId)
  const confirmSystems = useConfirmSystems(novelId)
  const rejectSystems = useRejectSystems(novelId)
  const [search, setSearch] = useState('')
  const [showTypeMenu, setShowTypeMenu] = useState(false)
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const [rejectAllConfirm, setRejectAllConfirm] = useState<number[] | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = (systems ?? []).filter((s) => {
      if (!q) return true
      const hay = `${s.name ?? ''} ${s.description ?? ''} ${s.display_type}`.toLowerCase()
      return hay.includes(q)
    })
    // Draft-first sorting: drafts first (newest at top), then confirmed by name
    return list.sort((a, b) => {
      if (a.status === 'draft' && b.status !== 'draft') return -1
      if (a.status !== 'draft' && b.status === 'draft') return 1
      if (a.status === 'draft' && b.status === 'draft') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      }
      return (a.name || '').localeCompare(b.name || '')
    })
  }, [systems, search])

  const draftIds = useMemo(() => filtered.filter((s) => s.status === 'draft').map((s) => s.id), [filtered])

  useEffect(() => {
    if (!selectedId) return
    const el = document.getElementById(`system-${selectedId}`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selectedId, systems])

  useEffect(() => {
    if (!showTypeMenu) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setShowTypeMenu(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [showTypeMenu])

  const handleCreate = (type: SystemDisplayType) => {
    setShowTypeMenu(false)
    createSystem.mutate(
      { name: '', display_type: type, data: INITIAL_DATA[type], constraints: [] },
      { onSuccess: (newSystem) => onSelect(newSystem) },
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 p-4 space-y-3">
        <Input
          placeholder={LABELS.SYSTEM_SEARCH_PLACEHOLDER}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 text-sm bg-transparent border-[var(--nw-glass-border)] placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="system-search"
        />
        <div className="relative">
          <button
            className="text-sm text-muted-foreground hover:text-foreground"
            onClick={() => setShowTypeMenu(!showTypeMenu)}
            data-testid="system-new"
          >
            {LABELS.SYSTEM_NEW}
          </button>
          {showTypeMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowTypeMenu(false)} />
              <GlassSurface
                variant="floating"
                className="absolute top-full left-0 mt-2 z-20 w-[220px] rounded-xl py-1"
              >
                {DISPLAY_TYPES.map(t => (
                  <button
                    key={t}
                    className="block w-full text-left px-4 py-2 text-sm hover:bg-[var(--nw-glass-bg-hover)]"
                    onClick={() => handleCreate(t)}
                  >
                    {getSystemDisplayTypeLabel(t)}
                  </button>
                ))}
              </GlassSurface>
            </>
          )}
        </div>

        {draftIds.length > 0 && (
          <div className="flex items-center gap-3">
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => confirmSystems.mutate(draftIds)}
              disabled={confirmSystems.isPending}
            >
              全部确认 ({draftIds.length})
            </button>
            <button
              className="text-xs text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)] rounded px-1 -mx-1 transition-colors"
              onClick={() => { if (draftIds.length > 0) setRejectAllConfirm(draftIds) }}
              disabled={rejectSystems.isPending}
            >
              全部拒绝 ({draftIds.length})
            </button>
          </div>
        )}
      </div>

      <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
        {filtered.map(sys => (
          <div
            key={sys.id}
            id={`system-${sys.id}`}
            className={cn(
              'group scroll-mb-64 flex items-center gap-3 px-4 py-2 cursor-pointer transition-colors border-l-2',
              selectedId === sys.id
                ? 'bg-[var(--nw-glass-bg-hover)] border-l-accent'
                : 'border-l-transparent hover:bg-[var(--nw-glass-bg-hover)]',
              sys.visibility === 'hidden' && 'opacity-60'
            )}
            onClick={() => onSelect(sys)}
            role="button"
            tabIndex={0}
            data-testid={`system-row-${sys.id}`}
            onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(sys)
              }
            }}
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate text-foreground">{sys.name || '\u00A0'}</div>
              {sys.description && <div className="text-xs text-muted-foreground line-clamp-1">{sys.description}</div>}
            </div>
            <span className="text-xs text-muted-foreground shrink-0">{getSystemDisplayTypeLabel(sys.display_type)}</span>
            {sys.constraints.length > 0 && (
              <span className="text-xs text-muted-foreground shrink-0">{sys.constraints.length}</span>
            )}
            <VisibilityDot
              visibility={sys.visibility}
              onChange={v => updateSystem.mutate({ systemId: sys.id, data: { visibility: v } })}
            />
            {sys.status === 'draft' ? (
              <span className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                <button
                  onClick={(e) => { e.stopPropagation(); confirmSystems.mutate([sys.id]) }}
                  className="rounded p-0.5 text-muted-foreground hover:text-[hsl(var(--color-status-confirmed))] hover:bg-[hsl(var(--color-status-confirmed)/0.10)] transition-colors"
                  title="确认"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); rejectSystems.mutate([sys.id]) }}
                  className="rounded p-0.5 text-muted-foreground hover:text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)] transition-colors"
                  title="拒绝"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </span>
            ) : (
              <button
                className={cn(
                  'text-xs shrink-0 opacity-0 group-hover:opacity-100 transition-opacity',
                  confirmId === sys.id ? 'text-[hsl(var(--color-danger))]' : 'text-muted-foreground hover:text-[hsl(var(--color-danger))]'
                )}
                onClick={e => {
                  e.stopPropagation()
                  if (confirmId === sys.id) {
                    deleteSystem.mutate(sys.id)
                    setConfirmId(null)
                  } else {
                    setConfirmId(sys.id)
                  }
                }}
                onMouseLeave={() => { if (confirmId === sys.id) setConfirmId(null) }}
              >
                {confirmId === sys.id ? LABELS.SYSTEM_DELETE_CONFIRM : '×'}
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="shrink-0 p-3 border-t border-[var(--nw-glass-border)] space-y-2">
        <WorldBuildPanel novelId={novelId} />
        <DraftReviewSummaryCard novelId={novelId} onOpen={onOpenDraftReview} />
      </div>

      <ConfirmDialog
        open={rejectAllConfirm !== null}
        tone="destructive"
        title="拒绝全部草稿体系？"
        description={
          rejectAllConfirm
            ? `将删除 ${rejectAllConfirm.length} 个草稿体系。\n此操作不可撤销。`
            : undefined
        }
        confirmText="拒绝并删除"
        onConfirm={() => {
          const ids = rejectAllConfirm ?? []
          setRejectAllConfirm(null)
          if (ids.length > 0) rejectSystems.mutate(ids)
        }}
        onClose={() => setRejectAllConfirm(null)}
      />
    </div>
  )
}
