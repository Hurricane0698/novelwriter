import { useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { getSystemDisplayTypeLabel } from '@/lib/worldSystemDisplay'
import { Input } from '@/components/ui/input'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldRelationships } from '@/hooks/world/useRelationships'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { buildDraftCleanupCopilotLaunchArgs } from '@/components/novel-copilot/novelCopilotLauncher'
import { Sparkles } from 'lucide-react'

export function DraftReviewNavigator({
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
  const { t } = useUiLocale()
  const { data: allEntities = [] } = useWorldEntities(novelId)
  const entityMap = useMemo(() => new Map(allEntities.map((e) => [e.id, e])), [allEntities])
  const copilot = useNovelCopilot()

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
        meta: getSystemDisplayTypeLabel(s.display_type),
      }))
  }, [draftEntities, draftRelationships, draftSystems, entityMap, kind, q])

  const totalCount = draftEntities.length + draftRelationships.length + draftSystems.length

  const jumpTo = (id: number) => {
    onSelectItem(kind, id)
    const el = document.getElementById(`draft-${kind}-${id}`) as HTMLElement | null
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  useEffect(() => {
    if (activeItemId == null) return
    const navigatorItem = document.querySelector(`[data-testid="draft-review-item-${activeItemId}"]`) as HTMLElement | null
    navigatorItem?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
    const contentItem = document.getElementById(`draft-${kind}-${activeItemId}`) as HTMLElement | null
    contentItem?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }, [activeItemId, kind])

  return (
    <div
      className={cn(
        'shrink-0 flex flex-col min-h-0 h-full w-[280px] overflow-hidden',
        'border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl',
        className,
      )}
      data-testid="draft-review-navigator"
    >
      <div className="shrink-0 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="text-sm font-medium text-foreground">{t('worldModel.common.draftReview')}</div>
          <span className="rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-xs tabular-nums text-[hsl(var(--color-status-draft))]">
            {totalCount}
          </span>
          {totalCount > 0 && (
            <button
              type="button"
              className="ml-auto flex items-center gap-1 rounded-full border border-[hsl(var(--foreground)/0.10)] bg-[hsl(var(--foreground)/0.05)] px-2 py-0.5 text-[10px] text-foreground/76 transition-colors hover:bg-[hsl(var(--foreground)/0.08)] hover:text-foreground"
              onClick={() => copilot.openDrawer(...buildDraftCleanupCopilotLaunchArgs({
                surface: 'atlas',
              }))}
            >
              <Sparkles className="h-3 w-3" /> {t('worldModel.draftReview.aiCleanup')}
            </button>
          )}
        </div>

        <Input
          placeholder={t('worldModel.common.searchDrafts')}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-9 text-sm bg-transparent border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="draft-review-search"
        />

        <div className="space-y-1">
          <KindButton active={kind === 'entities'} onClick={() => onKindChange('entities')}>
            {t('worldModel.common.entities')} <span className="ml-auto tabular-nums">{draftEntities.length}</span>
          </KindButton>
          <KindButton active={kind === 'relationships'} onClick={() => onKindChange('relationships')}>
            {t('worldModel.common.relationships')} <span className="ml-auto tabular-nums">{draftRelationships.length}</span>
          </KindButton>
          <KindButton active={kind === 'systems'} onClick={() => onKindChange('systems')}>
            {t('worldModel.common.systems')} <span className="ml-auto tabular-nums">{draftSystems.length}</span>
          </KindButton>
        </div>
      </div>

      <div className="nw-scrollbar-thin flex-1 min-h-0 overflow-y-auto px-2 pb-3">
        {listItems.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">{t('worldModel.draftReview.noMatches')}</div>
        ) : (
          listItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                'relative w-full overflow-hidden text-left px-3 py-2 transition-colors',
                activeItemId === item.id
                  ? 'nw-copilot-target-highlight border'
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
        'w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors border-l-2',
        active
          ? 'bg-accent/[0.06] text-accent border-accent'
          : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-foreground/5',
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
