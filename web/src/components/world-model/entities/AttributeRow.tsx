import { GripVertical } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { useUpdateAttribute, useDeleteAttribute } from '@/hooks/world/useEntities'
import { LABELS } from '@/constants/labels'
import type { WorldEntityAttribute } from '@/types/api'
import type { SyntheticListenerMap } from '@dnd-kit/core/dist/hooks/utilities'

export function AttributeRow({ novelId, entityId, attribute, dragListeners }: {
  novelId: number
  entityId: number
  attribute: WorldEntityAttribute
  dragListeners?: SyntheticListenerMap
}) {
  const { t } = useUiLocale()
  const updateAttr = useUpdateAttribute(novelId, entityId)
  const deleteAttr = useDeleteAttribute(novelId, entityId)

  const isHidden = attribute.visibility === 'hidden'

  return (
    <div
      className={cn(
        'group grid min-w-[520px] grid-cols-[16px_120px_1fr_1fr_44px_24px] items-stretch px-4 border-b border-[var(--nw-glass-border)]',
        isHidden && 'opacity-60',
      )}
      data-testid={`attribute-row-${attribute.id}`}
    >
      <div
        className="pt-3 text-muted-foreground/70 cursor-grab select-none"
        aria-label={t('worldModel.attribute.reorder')}
        title={t('worldModel.attribute.reorder')}
        {...dragListeners}
      >
        <GripVertical className="h-3.5 w-3.5" />
      </div>

      <div className="pr-2 py-3 min-w-0">
        <InlineEdit
          value={attribute.key}
          onSave={(v) => updateAttr.mutate({ attrId: attribute.id, data: { key: v } })}
          variant="transparent"
          className="text-sm font-medium text-foreground"
          placeholder={LABELS.PH_KEY}
        />
      </div>

      <div className="min-w-0 border-l border-border/40 bg-[hsl(var(--color-vis-reference)/0.035)] px-3 py-3">
        <InlineEdit
          value={attribute.surface}
          onSave={(v) => updateAttr.mutate({ attrId: attribute.id, data: { surface: v } })}
          multiline
          variant="transparent"
          className="text-sm text-foreground"
          placeholder={LABELS.PH_VALUE}
        />
      </div>

      <div className="min-w-0 border-l border-border/40 bg-[hsl(var(--color-mystery)/0.035)] px-3 py-3">
        <InlineEdit
          value={attribute.truth ?? ''}
          onSave={(v) => updateAttr.mutate({ attrId: attribute.id, data: { truth: v.trim() ? v : null } })}
          multiline
          variant="transparent"
          className="text-sm text-foreground"
          placeholder="—"
        />
      </div>

      <div className="flex justify-center pt-3">
        <VisibilityDot
          visibility={attribute.visibility}
          onChange={(v) => updateAttr.mutate({ attrId: attribute.id, data: { visibility: v } })}
        />
      </div>

      <div className="flex justify-end pt-3">
        <button
          type="button"
          className={cn(
            'text-xs text-muted-foreground/70 transition-opacity',
            'opacity-0 pointer-events-none',
            'group-hover:opacity-100 group-hover:pointer-events-auto',
            'group-focus-within:opacity-100 group-focus-within:pointer-events-auto',
            'focus-visible:opacity-100 focus-visible:pointer-events-auto',
            'hover:text-[hsl(var(--color-danger))] focus-visible:text-[hsl(var(--color-danger))]',
          )}
          onClick={() => deleteAttr.mutate(attribute.id)}
          aria-label={t('worldModel.attribute.delete')}
          title={t('worldModel.attribute.delete')}
        >
          ×
        </button>
      </div>
    </div>
  )
}
