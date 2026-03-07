import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldRelationships } from '@/hooks/world/useRelationships'
import { useWorldSystems } from '@/hooks/world/useSystems'
import type { DraftReviewKind } from '@/components/world-model/shared/DraftReviewPreview'

export function DraftReviewSidebar({
  novelId,
  kind,
  onKindChange,
  search,
  onSearchChange,
  activeItemId,
  onSelectItem,
  className,
}: {
  novelId: number
  kind: DraftReviewKind
  onKindChange: (k: DraftReviewKind) => void
  search: string
  onSearchChange: (v: string) => void
  activeItemId: number | null
  onSelectItem: (kind: DraftReviewKind, id: number) => void
  className?: string
}) {
  const { data: allEntities = [] } = useWorldEntities(novelId)
  const entityMap = useMemo(() => new Map(allEntities.map((e) => [e.id, e])), [allEntities])

  const { data: draftEntities = [] } = useWorldEntities(novelId, { status: 'draft' })
  const { data: draftRelationships = [] } = useWorldRelationships(novelId, { status: 'draft' })
  const { data: draftSystems = [] } = useWorldSystems(novelId, { status: 'draft' })
  const q = search.trim().toLowerCase()

  const listItems = useMemo(() => {
    if (kind === 'entities') {
      return draftEntities
        .filter((e) => {
          if (!q) return true
          return (
            e.name.toLowerCase().includes(q) ||
            (e.description ?? '').toLowerCase().includes(q) ||
            e.aliases?.some((a) => a.toLowerCase().includes(q))
          )
        })
        .map((e) => ({
          id: e.id,
          title: e.name || '\u00A0',
          meta: e.entity_type,
        }))
    }

    if (kind === 'relationships') {
      return draftRelationships
        .filter((r) => {
          if (!q) return true
          const left = entityMap.get(r.source_id)?.name ?? String(r.source_id)
          const right = entityMap.get(r.target_id)?.name ?? String(r.target_id)
          const hay = `${left} ${r.label} ${right} ${r.description ?? ''}`.toLowerCase()
          return hay.includes(q)
        })
        .map((r) => {
          const left = entityMap.get(r.source_id)?.name ?? String(r.source_id)
          const right = entityMap.get(r.target_id)?.name ?? String(r.target_id)
          return {
            id: r.id,
            title: `${left} — ${r.label} → ${right}`,
            meta: r.visibility,
          }
        })
    }

    return draftSystems
      .filter((s) => {
        if (!q) return true
        const hay = `${s.name ?? ''} ${s.description ?? ''} ${s.display_type}`.toLowerCase()
        return hay.includes(q)
      })
      .map((s) => ({
        id: s.id,
        title: s.name || '\u00A0',
        meta: s.display_type,
      }))
  }, [draftEntities, draftRelationships, draftSystems, entityMap, kind, q])

  const totalCount = draftEntities.length + draftRelationships.length + draftSystems.length

  const jumpTo = (id: number) => {
    onSelectItem(kind, id)
    const el = document.getElementById(`draft-${kind}-${id}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div
      className={cn(
        'shrink-0 flex flex-col min-h-0 h-full w-[280px]',
        'border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl',
        className,
      )}
      data-testid="draft-review-sidebar"
    >
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="text-sm font-medium text-foreground">草稿审核</div>
          <span className="ml-auto rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-xs tabular-nums text-[hsl(var(--color-status-draft))]">
            {totalCount}
          </span>
        </div>

        <Input
          placeholder="搜索草稿..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-9 text-sm bg-transparent border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="draft-review-search"
        />

        <div className="space-y-1">
          <KindButton active={kind === 'entities'} onClick={() => onKindChange('entities')}>
            实体 <span className="ml-auto tabular-nums">{draftEntities.length}</span>
          </KindButton>
          <KindButton active={kind === 'relationships'} onClick={() => onKindChange('relationships')}>
            关系 <span className="ml-auto tabular-nums">{draftRelationships.length}</span>
          </KindButton>
          <KindButton active={kind === 'systems'} onClick={() => onKindChange('systems')}>
            体系 <span className="ml-auto tabular-nums">{draftSystems.length}</span>
          </KindButton>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-3">
        {listItems.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">没有匹配项</div>
        ) : (
          listItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                'w-full text-left rounded-xl px-3 py-2 transition-colors',
                activeItemId === item.id
                  ? 'bg-[var(--nw-glass-bg-hover)] border border-[var(--nw-glass-border-hover)]'
                  : 'border border-transparent hover:bg-[var(--nw-glass-bg-hover)]',
              )}
              onClick={() => jumpTo(item.id)}
              title={item.title}
              data-testid={`draft-review-item-${item.id}`}
            >
              <div className="text-sm text-foreground truncate">{item.title}</div>
              <div className="text-xs text-muted-foreground truncate">{item.meta}</div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}

function KindButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className={cn(
        'w-full flex items-center gap-2 rounded-xl px-3 py-2 text-xs transition-colors border',
        active
          ? 'bg-[var(--nw-glass-bg-hover)] text-foreground border-[var(--nw-glass-border-hover)]'
          : 'border-[var(--nw-glass-border)] text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)]',
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
