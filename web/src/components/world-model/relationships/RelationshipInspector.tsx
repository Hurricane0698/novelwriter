import { useMemo, useState } from 'react'
import { Link2, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Button } from '@/components/ui/button'
import { LABELS } from '@/constants/labels'
import type { WorldEntity, WorldRelationship, UpdateRelationshipRequest } from '@/types/api'

export function RelationshipInspector({
  rel,
  entities,
  onUpdate,
  onConfirm,
  onDelete,
  className,
}: {
  rel: WorldRelationship | null
  entities: WorldEntity[]
  onUpdate: (relId: number, data: UpdateRelationshipRequest) => void
  onConfirm: (relId: number) => void
  onDelete: (relId: number) => void
  className?: string
}) {
  const [pendingDeleteRelId, setPendingDeleteRelId] = useState<number | null>(null)
  const entityMap = useMemo(() => new Map(entities.map((e) => [e.id, e])), [entities])

  const leftName = rel ? (entityMap.get(rel.source_id)?.name ?? String(rel.source_id)) : ''
  const rightName = rel ? (entityMap.get(rel.target_id)?.name ?? String(rel.target_id)) : ''

  return (
    <>
      <div
        className={cn(
          'h-[160px] shrink-0 flex items-start gap-6 px-8 py-5',
          'border-t border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl',
          className,
        )}
        data-testid="relationship-inspector"
      >
        <div className="w-[240px] shrink-0 space-y-2">
          {rel ? (
            <>
              <div className="text-sm font-mono text-foreground truncate">
                {leftName} <span className="text-muted-foreground">→</span> {rightName}
              </div>
              <div className="flex items-center gap-2">
                <VisibilityDot
                  visibility={rel.visibility}
                  onChange={(v) => onUpdate(rel.id, { visibility: v })}
                />
                <div className="inline-flex items-center gap-1 rounded border border-[hsl(var(--color-accent)/0.28)] bg-[hsl(var(--color-accent)/0.10)] px-2 py-1 text-[11px] text-[hsl(var(--color-accent))]">
                  <Link2 className="h-3 w-3" />
                  <InlineEdit
                    value={rel.label}
                    onSave={(v) => onUpdate(rel.id, { label: v })}
                    variant="bare"
                    className="font-medium"
                    placeholder={LABELS.REL_LABEL_PLACEHOLDER}
                  />
                </div>
              </div>
              {rel.status === 'draft' ? (
                <div className="text-xs text-[hsl(var(--color-status-draft))]">
                  ● {LABELS.STATUS_DRAFT}
                </div>
              ) : null}
            </>
          ) : (
            <div className="text-sm text-muted-foreground">
              {LABELS.REL_INSPECTOR_EMPTY}
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          <div className="text-[11px] font-semibold tracking-wider text-muted-foreground">
            {LABELS.REL_DESCRIPTION}
          </div>
          {rel ? (
            <InlineEdit
              value={rel.description ?? ''}
              onSave={(v) => onUpdate(rel.id, { description: v })}
              multiline
              variant="transparent"
              className="text-sm text-foreground"
              placeholder={LABELS.REL_DESCRIPTION_PLACEHOLDER}
            />
          ) : (
            <div className="text-sm text-muted-foreground">
              {LABELS.REL_INSPECTOR_HINT}
            </div>
          )}
        </div>

        <div className="shrink-0 flex flex-col gap-2">
          {rel?.status === 'draft' ? (
            <Button
              size="sm"
              onClick={() => onConfirm(rel.id)}
              data-testid="relationship-inspector-confirm"
            >
              {LABELS.CONFIRM}
            </Button>
          ) : null}
          {rel ? (
            <Button
              size="sm"
              variant="outline"
              className="border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)] text-[hsl(var(--color-danger))] hover:text-[hsl(var(--color-danger))]"
              onClick={() => setPendingDeleteRelId(rel.id)}
              data-testid="relationship-inspector-delete"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              {LABELS.REL_DELETE}
            </Button>
          ) : null}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDeleteRelId != null && pendingDeleteRelId === rel?.id}
        title={LABELS.REL_DELETE}
        description={LABELS.REL_DELETE_CONFIRM}
        confirmText={LABELS.CONFIRM}
        cancelText={LABELS.CANCEL}
        tone="destructive"
        onConfirm={() => {
          if (pendingDeleteRelId == null) return
          setPendingDeleteRelId(null)
          onDelete(pendingDeleteRelId)
        }}
        onClose={() => setPendingDeleteRelId(null)}
      />
    </>
  )
}
