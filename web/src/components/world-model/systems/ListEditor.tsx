import { useState } from 'react'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { LABELS } from '@/constants/labels'
import type { Visibility } from '@/types/api'

interface ListItem {
  label: string
  description: string
  visibility: Visibility
}

interface ListData {
  items: ListItem[]
}

export function ListEditor({ data, onUpdate }: {
  data: ListData
  onUpdate: (data: ListData) => void
}) {
  const [hovered, setHovered] = useState<number | null>(null)
  const items = data.items ?? []

  const update = (i: number, patch: Partial<ListItem>) => {
    const next = items.map((item, j) => j === i ? { ...item, ...patch } : item)
    onUpdate({ items: next })
  }

  const remove = (i: number) => onUpdate({ items: items.filter((_, j) => j !== i) })

  const add = () => onUpdate({ items: [...items, { label: '', description: '', visibility: 'active' }] })

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div
          key={i}
          className="flex items-start gap-2 px-3 py-2 rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
          onMouseEnter={() => setHovered(i)}
          onMouseLeave={() => setHovered(null)}
        >
          <span className="text-muted-foreground text-xs mt-1 cursor-grab select-none">⠿</span>
          <VisibilityDot visibility={item.visibility ?? 'active'} onChange={v => update(i, { visibility: v })} className="mt-1" />
          <div className="flex-1 min-w-0">
            <div>
              <InlineEdit value={item.label} onSave={v => update(i, { label: v })} className="text-sm font-medium" placeholder={LABELS.PH_NAME} />
            </div>
            <div className="mt-1">
              <InlineEdit value={item.description} onSave={v => update(i, { description: v })} multiline className="text-xs text-muted-foreground/80" placeholder={LABELS.PH_DESCRIPTION} />
            </div>
          </div>
          {hovered === i && (
            <button
              className="text-muted-foreground hover:text-[hsl(var(--color-danger))] text-xs mt-1"
              onClick={() => remove(i)}
            >×</button>
          )}
        </div>
      ))}
      <button className="text-sm text-muted-foreground hover:text-foreground px-3 py-1" onClick={add}>
        {LABELS.SYSTEM_ADD_ITEM}
      </button>
    </div>
  )
}
