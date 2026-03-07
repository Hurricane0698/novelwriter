import { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'

export type InlineEditVariant = 'glass' | 'transparent' | 'bare'

export function InlineEdit({ value, onSave, multiline, className, placeholder, autoFocus, variant }: {
  value: string
  onSave: (v: string) => void
  multiline?: boolean
  className?: string
  placeholder?: string
  autoFocus?: boolean
  /** Visual preset for the editable surface. */
  variant?: InlineEditVariant
}) {
  const [editing, setEditing] = useState(autoFocus ?? false)
  const [draft, setDraft] = useState(value)
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editing) ref.current?.focus()
  }, [editing])

  const save = () => {
    setEditing(false)
    if (draft !== value) onSave(draft)
  }

  const cancel = () => {
    setEditing(false)
    setDraft(value)
  }

  if (!editing) {
    return (
      <span
        className={cn(
          'cursor-pointer rounded px-1 -mx-1 transition-colors',
          (variant ?? 'glass') === 'glass' ? 'hover:bg-[var(--nw-glass-bg-hover)]' : null,
          className
        )}
        onClick={() => { setDraft(value); setEditing(true) }}
        data-testid="inline-edit-display"
      >
        {value || (placeholder ? <span className="text-muted-foreground/50">{placeholder}</span> : '\u00A0')}
      </span>
    )
  }

  const v = variant ?? 'glass'
  const props = {
    ref: ref as never,
    value: draft,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(e.target.value),
    onBlur: save,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') cancel()
      if (e.key === 'Enter' && !multiline) save()
    },
    className: cn(
      'w-full rounded px-1 py-0.5 text-sm text-foreground placeholder:text-muted-foreground/70',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0',
      v === 'glass'
        ? 'border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]'
        : v === 'transparent'
          ? 'border border-[var(--nw-glass-border)] bg-transparent'
          : 'border-0 bg-transparent px-0 py-0',
      className
    ),
    'data-testid': 'inline-edit-input',
  }

  return multiline ? <textarea {...props} rows={3} /> : <input {...props} />
}
