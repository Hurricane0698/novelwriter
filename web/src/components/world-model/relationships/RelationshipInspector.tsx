import { useMemo, useState } from 'react'
import { Link2, Trash2, X } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
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
  onClose,
  allowDelete = true,
  layout = 'compact',
  className,
}: {
  rel: WorldRelationship | null
  entities: WorldEntity[]
  onUpdate: (relId: number, data: UpdateRelationshipRequest) => void
  onConfirm: (relId: number) => void
  onDelete: (relId: number) => void
  onClose?: () => void
  allowDelete?: boolean
  layout?: 'compact' | 'full'
  className?: string
}) {
  const { t } = useUiLocale()
  const [pendingDeleteRelId, setPendingDeleteRelId] = useState<number | null>(null)
  const entityMap = useMemo(() => new Map(entities.map((e) => [e.id, e])), [entities])

  const leftName = rel ? (entityMap.get(rel.source_id)?.name ?? String(rel.source_id)) : ''
  const rightName = rel ? (entityMap.get(rel.target_id)?.name ?? String(rel.target_id)) : ''

  return (
    <>
      <div
        className={cn(
          layout === 'full'
            ? 'relative flex h-full min-h-0 flex-wrap items-start gap-5 overflow-y-auto px-6 py-5'
            : 'relative max-h-[35%] min-h-[128px] shrink-0 flex flex-wrap items-start gap-5 overflow-y-auto px-6 py-4 pr-12',
          layout === 'full'
            ? 'bg-background'
            : 'border-t border-[var(--nw-glass-border)] bg-background',
          className,
        )}
        data-testid="relationship-inspector"
      >
        {onClose && <button type="button" onClick={onClose} aria-label={t('worldModel.graph.closeInspector')} className="absolute right-3 top-3 rounded p-1.5 text-muted-foreground hover:bg-foreground/5"><X size={14} /></button>}
        <div className="min-w-0 basis-[200px] shrink-0 space-y-2">
          {rel ? (
            <>
              <div className="text-sm font-medium text-foreground truncate">
                {leftName} <span className="text-muted-foreground">→</span> {rightName}
              </div>
              <div className="flex items-center gap-2">
                <VisibilityDot
                  visibility={rel.visibility}
                  onChange={(v) => onUpdate(rel.id, { visibility: v })}
                />
                <div className="inline-flex items-center gap-1 py-1 text-xs text-accent">
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

        <div className="min-w-[160px] flex-1 space-y-2">
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
          {rel && allowDelete ? (
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
        open={allowDelete && pendingDeleteRelId != null && pendingDeleteRelId === rel?.id}
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
