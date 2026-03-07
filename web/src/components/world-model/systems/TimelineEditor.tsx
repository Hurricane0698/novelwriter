import { useState } from 'react'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { LABELS } from '@/constants/labels'
import type { Visibility } from '@/types/api'

interface TimelineEvent {
  time: string
  label: string
  description: string
  visibility: Visibility
}

interface TimelineData {
  events: TimelineEvent[]
}

export function TimelineEditor({ data, onUpdate }: {
  data: TimelineData
  onUpdate: (data: TimelineData) => void
}) {
  const [hovered, setHovered] = useState<number | null>(null)
  const events = data.events ?? []

  const update = (i: number, patch: Partial<TimelineEvent>) => {
    const next = events.map((ev, j) => j === i ? { ...ev, ...patch } : ev)
    onUpdate({ events: next })
  }

  const remove = (i: number) => onUpdate({ events: events.filter((_, j) => j !== i) })

  const add = () => onUpdate({ events: [...events, { time: '', label: '', description: '', visibility: 'active' }] })

  return (
    <div className="space-y-0">
      {events.map((ev, i) => (
        <div
          key={i}
          className="flex gap-4 group"
          onMouseEnter={() => setHovered(i)}
          onMouseLeave={() => setHovered(null)}
        >
          <div className="w-24 shrink-0 text-right pt-2">
            <InlineEdit value={ev.time} onSave={v => update(i, { time: v })} className="text-xs text-muted-foreground" placeholder={LABELS.PH_TIME} />
          </div>
          <div className="flex flex-col items-center">
            <div className="w-2.5 h-2.5 rounded-full bg-accent shrink-0 mt-2.5" />
            {i < events.length - 1 && <div className="w-px flex-1 bg-[var(--nw-glass-border)]" />}
          </div>
          <div className="flex-1 pb-4 pt-1">
            <div className="flex items-start gap-2 rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl px-3 py-2">
              <VisibilityDot visibility={ev.visibility ?? 'active'} onChange={v => update(i, { visibility: v })} className="mt-0.5" />
              <div className="flex-1 min-w-0">
                <div>
                  <InlineEdit value={ev.label} onSave={v => update(i, { label: v })} className="text-sm font-medium" placeholder={LABELS.PH_EVENT_NAME} />
                </div>
                <div className="mt-1">
                  <InlineEdit value={ev.description} onSave={v => update(i, { description: v })} multiline className="text-xs text-muted-foreground/80" placeholder={LABELS.PH_DESCRIPTION} />
                </div>
              </div>
              {hovered === i && (
                <button
                  className="text-muted-foreground hover:text-[hsl(var(--color-danger))] text-xs"
                  onClick={() => remove(i)}
                >×</button>
              )}
            </div>
          </div>
        </div>
      ))}
      <div className="flex gap-4">
        <div className="w-24" />
        <div className="flex flex-col items-center"><div className="w-px h-2" /></div>
        <button className="text-sm text-muted-foreground hover:text-foreground py-1" onClick={add}>
          {LABELS.SYSTEM_ADD_EVENT}
        </button>
      </div>
    </div>
  )
}
