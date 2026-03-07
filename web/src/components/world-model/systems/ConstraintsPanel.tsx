import { useState } from 'react'
import { cn } from '@/lib/utils'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { LABELS } from '@/constants/labels'

export function ConstraintsPanel({ constraints, onChange }: {
  constraints: string[]
  onChange: (constraints: string[]) => void
}) {
  const [open, setOpen] = useState(true)
  const [hovered, setHovered] = useState<number | null>(null)

  const update = (i: number, v: string) => {
    const next = [...constraints]
    next[i] = v
    onChange(next)
  }

  const remove = (i: number) => onChange(constraints.filter((_, j) => j !== i))

  const add = () => onChange([...constraints, ''])

  return (
    <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-3">
      <button
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        onClick={() => setOpen(!open)}
      >
        <span className="text-xs">{open ? '▼' : '▶'}</span>
        {LABELS.SYSTEM_CONSTRAINTS} ({constraints.length})
      </button>
      <div className={cn(
        'grid transition-[grid-template-rows] duration-200',
        open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
      )}>
        <div className="overflow-hidden">
          <div className="mt-2 space-y-1">
            {constraints.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              >
                <span className="text-muted-foreground text-xs">{i + 1}.</span>
                <InlineEdit value={c} onSave={v => update(i, v)} className="text-sm flex-1" placeholder={LABELS.PH_CONSTRAINT} />
                {hovered === i && (
                  <button
                    className="text-muted-foreground hover:text-[hsl(var(--color-danger))] text-xs"
                    onClick={() => remove(i)}
                  >×</button>
                )}
              </div>
            ))}
            <button
              className="text-sm text-muted-foreground hover:text-foreground px-2 py-1"
              onClick={add}
            >{LABELS.SYSTEM_ADD_CONSTRAINT}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
