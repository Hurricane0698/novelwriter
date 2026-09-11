import { useMemo, useState } from 'react'
import '@/lib/uiMessagePacks/novel'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useWorldEntities, useConfirmEntities, useRejectEntities } from '@/hooks/world/useEntities'
import { useWorldRelationships, useConfirmRelationships, useRejectRelationships } from '@/hooks/world/useRelationships'
import { useWorldSystems, useConfirmSystems, useRejectSystems } from '@/hooks/world/useSystems'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getSystemDisplayTypeLabel } from '@/lib/worldSystemDisplay'
import type { WorldEntity, WorldRelationship, WorldSystem } from '@/types/api'

type ReviewKind = 'entities' | 'relationships' | 'systems'

export function DraftReviewTab({
  novelId,
  onOpenEntity,
  onOpenRelationships,
  onOpenSystem,
  initialKind = 'entities',
  kind: kindProp,
  onKindChange,
  search = '',
  showKindSelector = true,
  showBatchActions = true,
  highlightId,
}: {
  novelId: number
  onOpenEntity: (entityId: number) => void
  onOpenRelationships: (entityId: number) => void
  onOpenSystem?: (systemId: number) => void
  initialKind?: ReviewKind
  kind?: ReviewKind
  onKindChange?: (k: ReviewKind) => void
  search?: string
  showKindSelector?: boolean
  showBatchActions?: boolean
  highlightId?: number | null
}) {
  const { t } = useUiLocale()
  const [kindInternal, setKindInternal] = useState<ReviewKind>(initialKind)
  const kind = kindProp ?? kindInternal
  const setKind = onKindChange ?? setKindInternal

  const { data: allEntities = [] } = useWorldEntities(novelId)
  const entityMap = useMemo(() => new Map(allEntities.map(e => [e.id, e])), [allEntities])

  const { data: draftEntities = [] } = useWorldEntities(novelId, { status: 'draft' })
  const { data: draftRelationships = [] } = useWorldRelationships(novelId, { status: 'draft' })
  const { data: draftSystems = [] } = useWorldSystems(novelId, { status: 'draft' })

  const q = search.trim().toLowerCase()

  const filteredDraftEntities = useMemo(() => {
    if (!q) return draftEntities
    return draftEntities.filter((e) => {
      return (
        e.name.toLowerCase().includes(q) ||
        (e.description ?? '').toLowerCase().includes(q) ||
        e.aliases?.some((a) => a.toLowerCase().includes(q))
      )
    })
  }, [draftEntities, q])

  const filteredDraftRelationships = useMemo(() => {
    if (!q) return draftRelationships
    return draftRelationships.filter((r) => {
      const left = entityMap.get(r.source_id)?.name ?? String(r.source_id)
      const right = entityMap.get(r.target_id)?.name ?? String(r.target_id)
      const hay = `${left} ${r.label} ${right} ${r.description ?? ''}`.toLowerCase()
      return hay.includes(q)
    })
  }, [draftRelationships, entityMap, q])

  const filteredDraftSystems = useMemo(() => {
    if (!q) return draftSystems
    return draftSystems.filter((s) => {
      const hay = `${s.name ?? ''} ${s.description ?? ''} ${s.display_type}`.toLowerCase()
      return hay.includes(q)
    })
  }, [draftSystems, q])

  const confirmEntities = useConfirmEntities(novelId)
  const rejectEntities = useRejectEntities(novelId)
  const confirmRelationships = useConfirmRelationships(novelId)
  const rejectRelationships = useRejectRelationships(novelId)
  const confirmSystems = useConfirmSystems(novelId)
  const rejectSystems = useRejectSystems(novelId)

  const [rejectAllConfirm, setRejectAllConfirm] = useState<{ kind: ReviewKind; ids: number[] } | null>(null)

  const itemsForKind = useMemo(() => {
    if (kind === 'entities') return filteredDraftEntities
    if (kind === 'relationships') return filteredDraftRelationships
    return filteredDraftSystems
  }, [kind, filteredDraftEntities, filteredDraftRelationships, filteredDraftSystems])

  const idsForKind = useMemo(() => itemsForKind.map((item) => item.id), [itemsForKind])

  const handleConfirmAll = () => {
    if (idsForKind.length === 0) return
    if (kind === 'entities') confirmEntities.mutate(idsForKind)
    else if (kind === 'relationships') confirmRelationships.mutate(idsForKind)
    else confirmSystems.mutate(idsForKind)
  }

  const handleRejectAll = () => {
    if (idsForKind.length === 0) return
    setRejectAllConfirm({ kind, ids: idsForKind })
  }

  const kindLabels: Record<ReviewKind, string> = {
    entities: t('worldModel.common.entities'),
    relationships: t('worldModel.common.relationships'),
    systems: t('worldModel.common.systems'),
  }
  const rejectAllKindLabel = rejectAllConfirm ? kindLabels[rejectAllConfirm.kind] : ''

  const handleConfirmRejectAll = () => {
    if (!rejectAllConfirm) return
    const { kind: k, ids } = rejectAllConfirm
    if (ids.length === 0) {
      setRejectAllConfirm(null)
      return
    }
    if (k === 'entities') rejectEntities.mutate(ids)
    else if (k === 'relationships') rejectRelationships.mutate(ids)
    else rejectSystems.mutate(ids)
    setRejectAllConfirm(null)
  }

  return (
    <>
      <div className="flex-1 flex flex-col min-h-0 p-4 gap-4">
        <div className="flex items-center gap-3">
          {showKindSelector ? (
            <div className="inline-flex rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-1">
              <KindButton active={kind === 'entities'} onClick={() => setKind('entities')}>
                {kindLabels.entities} ({draftEntities.length})
              </KindButton>
              <KindButton active={kind === 'relationships'} onClick={() => setKind('relationships')}>
                {kindLabels.relationships} ({draftRelationships.length})
              </KindButton>
              <KindButton active={kind === 'systems'} onClick={() => setKind('systems')}>
                {kindLabels.systems} ({draftSystems.length})
              </KindButton>
            </div>
          ) : (
            <div className="text-sm font-semibold text-foreground">
              {kind === 'entities'
                ? `${kindLabels.entities} (${draftEntities.length})`
                : kind === 'relationships'
                  ? `${kindLabels.relationships} (${draftRelationships.length})`
                  : `${kindLabels.systems} (${draftSystems.length})`}
            </div>
          )}

          {showBatchActions ? (
            <div className="ml-auto flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-8"
                onClick={handleConfirmAll}
                disabled={idsForKind.length === 0 || confirmEntities.isPending || confirmRelationships.isPending || confirmSystems.isPending}
              >
                {t('dialog.confirm')} {t('worldModel.common.all')} ({idsForKind.length})
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 border-[hsl(var(--color-danger)/0.2)] bg-transparent text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.08)] hover:text-[hsl(var(--color-danger))]"
                onClick={handleRejectAll}
                disabled={idsForKind.length === 0 || rejectEntities.isPending || rejectRelationships.isPending || rejectSystems.isPending}
              >
                {t('worldModel.common.reject')} {t('worldModel.common.all')} ({idsForKind.length})
              </Button>
            </div>
          ) : null}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-3">
          {kind === 'entities' ? (
            filteredDraftEntities.length === 0 ? (
              <EmptyState />
            ) : (
              filteredDraftEntities.map((e) => (
                <EntityDraftCard
                  key={e.id}
                  entity={e}
                  highlighted={highlightId === e.id}
                  onConfirm={() => confirmEntities.mutate([e.id])}
                  onReject={() => rejectEntities.mutate([e.id])}
                  onOpen={() => onOpenEntity(e.id)}
                />
              ))
            )
          ) : kind === 'relationships' ? (
            filteredDraftRelationships.length === 0 ? (
              <EmptyState />
            ) : (
              filteredDraftRelationships.map((r) => (
                <RelationshipDraftCard
                  key={r.id}
                  rel={r}
                  source={entityMap.get(r.source_id)}
                  target={entityMap.get(r.target_id)}
                  highlighted={highlightId === r.id}
                  onConfirm={() => confirmRelationships.mutate([r.id])}
                  onReject={() => rejectRelationships.mutate([r.id])}
                  onOpen={() => onOpenRelationships(r.source_id)}
                />
              ))
            )
          ) : filteredDraftSystems.length === 0 ? (
            <EmptyState />
          ) : (
            filteredDraftSystems.map((s) => (
              <SystemDraftCard
                key={s.id}
                system={s}
                highlighted={highlightId === s.id}
                onConfirm={() => confirmSystems.mutate([s.id])}
                onReject={() => rejectSystems.mutate([s.id])}
                onOpen={onOpenSystem ? () => onOpenSystem(s.id) : undefined}
              />
            ))
          )}
        </div>
      </div>

      <ConfirmDialog
        open={rejectAllConfirm !== null}
        tone="destructive"
        title={t('worldModel.draftReview.rejectAllTitle', { kind: rejectAllKindLabel })}
        description={
          rejectAllConfirm
            ? t('worldModel.draftReview.rejectAllDescription', {
              count: rejectAllConfirm.ids.length,
              kind: rejectAllKindLabel,
            })
            : undefined
        }
        confirmText={t('worldModel.draftReview.rejectAndDelete')}
        onConfirm={handleConfirmRejectAll}
        onClose={() => setRejectAllConfirm(null)}
      />
    </>
  )
}

function KindButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      className={cn(
        'px-3 py-1.5 text-xs rounded-full transition-colors',
        active ? 'bg-[var(--nw-glass-bg-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground',
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function CardShell({ id, highlighted, className, children }: { id?: string; highlighted?: boolean; className?: string; children: React.ReactNode }) {
  return (
    <div
      id={id}
      className={cn(
        'relative overflow-hidden border-b px-4 py-5 transition-colors',
        highlighted
          ? 'nw-copilot-target-highlight'
          : 'border-[var(--nw-glass-border)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

function EmptyState() {
  const { t } = useUiLocale()
  return (
    <div className="h-40 flex items-center justify-center text-sm text-muted-foreground">
      {t('worldModel.draftReview.noDrafts')}
    </div>
  )
}

function EntityDraftCard({
  entity,
  highlighted,
  onConfirm,
  onReject,
  onOpen,
}: {
  entity: WorldEntity
  highlighted?: boolean
  onConfirm: () => void
  onReject: () => void
  onOpen: () => void
}) {
  const { t } = useUiLocale()
  return (
    <CardShell id={`draft-entities-${entity.id}`} highlighted={highlighted}>
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold truncate">{entity.name}</div>
            <span className="text-xs text-muted-foreground">{entity.entity_type}</span>
            <span className="text-xs text-[hsl(var(--color-status-draft))]">● {t('worldModel.common.statusDraft')}</span>
          </div>
          {entity.description ? (
            <div className="text-xs text-muted-foreground line-clamp-2">{entity.description}</div>
          ) : null}
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <Button size="sm" variant="outline" className="h-8" onClick={onOpen}>
            {t('worldModel.common.view')}
          </Button>
          <Button size="sm" variant="outline" className="h-8" onClick={onConfirm}>
            {t('dialog.confirm')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 border-[hsl(var(--color-danger)/0.2)] bg-transparent text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.08)] hover:text-[hsl(var(--color-danger))]"
            onClick={onReject}
          >
            {t('worldModel.common.reject')}
          </Button>
        </div>
      </div>
    </CardShell>
  )
}

function RelationshipDraftCard({
  rel,
  source,
  target,
  highlighted,
  onConfirm,
  onReject,
  onOpen,
}: {
  rel: WorldRelationship
  source: WorldEntity | undefined
  target: WorldEntity | undefined
  highlighted?: boolean
  onConfirm: () => void
  onReject: () => void
  onOpen: () => void
}) {
  const { t } = useUiLocale()
  const left = source?.name ?? String(rel.source_id)
  const right = target?.name ?? String(rel.target_id)
  return (
    <CardShell id={`draft-relationships-${rel.id}`} highlighted={highlighted}>
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold truncate">
              {left} <span className="text-muted-foreground">—</span> {rel.label} <span className="text-muted-foreground">→</span> {right}
            </div>
            <span className="text-xs text-[hsl(var(--color-status-draft))]">● {t('worldModel.common.statusDraft')}</span>
          </div>
          {rel.description ? (
            <div className="text-xs text-muted-foreground line-clamp-2">{rel.description}</div>
          ) : null}
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <Button size="sm" variant="outline" className="h-8" onClick={onOpen}>
            {t('worldModel.common.locate')}
          </Button>
          <Button size="sm" variant="outline" className="h-8" onClick={onConfirm}>
            {t('dialog.confirm')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 border-[hsl(var(--color-danger)/0.2)] bg-transparent text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.08)] hover:text-[hsl(var(--color-danger))]"
            onClick={onReject}
          >
            {t('worldModel.common.reject')}
          </Button>
        </div>
      </div>
    </CardShell>
  )
}

function SystemDraftCard({
  system,
  highlighted,
  onConfirm,
  onReject,
  onOpen,
}: {
  system: WorldSystem
  highlighted?: boolean
  onConfirm: () => void
  onReject: () => void
  onOpen?: () => void
}) {
  const { locale, t } = useUiLocale()
  return (
    <CardShell id={`draft-systems-${system.id}`} highlighted={highlighted}>
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold truncate">{system.name || '\u00A0'}</div>
            <span className="text-xs text-muted-foreground">{getSystemDisplayTypeLabel(system.display_type, locale)}</span>
            <span className="text-xs text-[hsl(var(--color-status-draft))]">● {t('worldModel.common.statusDraft')}</span>
          </div>
          {system.description ? (
            <div className="text-xs text-muted-foreground line-clamp-2">{system.description}</div>
          ) : null}
        </div>
        <div className="shrink-0 flex items-center gap-2">
          {onOpen ? (
            <Button size="sm" variant="outline" className="h-8" onClick={onOpen}>
              {t('worldModel.common.view')}
            </Button>
          ) : null}
          <Button size="sm" variant="outline" className="h-8" onClick={onConfirm}>
            {t('dialog.confirm')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 border-[hsl(var(--color-danger)/0.2)] bg-transparent text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.08)] hover:text-[hsl(var(--color-danger))]"
            onClick={onReject}
          >
            {t('worldModel.common.reject')}
          </Button>
        </div>
      </div>
    </CardShell>
  )
}
