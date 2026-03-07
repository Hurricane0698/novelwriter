import { useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useWorldRelationships, useConfirmRelationships, useRejectRelationships } from '@/hooks/world/useRelationships'
import { LABELS } from '@/constants/labels'

export function RelationshipSidebarSection({
  novelId,
  selectedEntityId,
  onRequestNewRelationship,
  onOpenDraftReview,
  className,
}: {
  novelId: number
  selectedEntityId: number | null
  onRequestNewRelationship: () => void
  onOpenDraftReview: () => void
  className?: string
}) {
  const { data: relationships = [] } = useWorldRelationships(
    novelId,
    selectedEntityId !== null ? { entity_id: selectedEntityId } : undefined,
    selectedEntityId !== null,
  )
  const confirmRels = useConfirmRelationships(novelId)
  const rejectRels = useRejectRelationships(novelId)
  const [rejectAllConfirm, setRejectAllConfirm] = useState(false)

  const draftRelationships = useMemo(
    () => relationships.filter((r) => r.status === 'draft'),
    [relationships],
  )
  const draftIds = useMemo(() => draftRelationships.map((r) => r.id), [draftRelationships])

  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-3 space-y-2',
        className,
      )}
      data-testid="relationship-sidebar-section"
    >
      <div className="flex items-center gap-2">
        <div className="text-sm font-medium text-foreground">关系</div>
        <span className="rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
          {relationships.length}
        </span>
        {draftRelationships.length > 0 ? (
          <span className="rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-xs tabular-nums text-[hsl(var(--color-status-draft))]">
            draft {draftRelationships.length}
          </span>
        ) : null}
        <Button
          size="sm"
          className="ml-auto h-8"
          onClick={onRequestNewRelationship}
          disabled={selectedEntityId === null}
          data-testid="sidebar-rel-new"
        >
          {LABELS.REL_NEW}
        </Button>
      </div>

      {selectedEntityId === null ? (
        <div className="text-xs text-muted-foreground">选择一个实体查看关系</div>
      ) : draftRelationships.length === 0 ? (
        <div className="text-xs text-muted-foreground">暂无草稿关系</div>
      ) : (
        <div className="space-y-1">
          {draftRelationships.slice(0, 3).map((r) => (
            <div
              key={r.id}
              className="flex items-center gap-2 rounded-lg px-2 py-1 text-xs text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)]"
              title={r.description || r.label}
            >
              <span className="truncate flex-1">{r.label || '\u00A0'}</span>
              <button
                type="button"
                className="rounded px-1 py-0.5 text-muted-foreground hover:text-[hsl(var(--color-status-confirmed))] hover:bg-[hsl(var(--color-status-confirmed)/0.10)] transition-colors"
                onClick={() => confirmRels.mutate([r.id])}
                title={LABELS.CONFIRM}
                aria-label={LABELS.CONFIRM}
              >
                ✓
              </button>
              <button
                type="button"
                className="rounded px-1 py-0.5 text-muted-foreground hover:text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)] transition-colors"
                onClick={() => rejectRels.mutate([r.id])}
                title="拒绝"
                aria-label="拒绝"
              >
                ×
              </button>
            </div>
          ))}
          {draftRelationships.length > 3 ? (
            <button
              type="button"
              className="w-full rounded-lg px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] text-left"
              onClick={onOpenDraftReview}
            >
              查看全部草稿关系…
            </button>
          ) : null}
        </div>
      )}

      {draftIds.length > 0 ? (
        <div className="flex items-center gap-2 pt-1">
          <Button
            size="sm"
            variant="outline"
            className="h-8 flex-1 border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)]"
            onClick={() => confirmRels.mutate(draftIds)}
            disabled={confirmRels.isPending}
          >
            {LABELS.CONFIRM_ALL_RELATIONSHIPS} ({draftIds.length})
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 flex-1 border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)] text-[hsl(var(--color-danger))] hover:text-[hsl(var(--color-danger))]"
            onClick={() => setRejectAllConfirm(true)}
            disabled={rejectRels.isPending}
          >
            拒绝全部 ({draftIds.length})
          </Button>
        </div>
      ) : null}

      <ConfirmDialog
        open={rejectAllConfirm}
        tone="destructive"
        title="拒绝全部草稿关系？"
        description={`将删除 ${draftIds.length} 条草稿关系。\n此操作不可撤销。`}
        confirmText="拒绝并删除"
        onConfirm={() => {
          setRejectAllConfirm(false)
          if (draftIds.length > 0) rejectRels.mutate(draftIds)
        }}
        onClose={() => setRejectAllConfirm(false)}
      />
    </div>
  )
}
