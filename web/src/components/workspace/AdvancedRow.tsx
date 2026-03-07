import { Input } from '@/components/ui/input'

export function AdvancedRow({
  label,
  desc,
  value,
  onChange,
  type = 'text',
  min,
  max,
  step,
}: {
  label: string
  desc?: string
  value: string
  onChange: (v: string) => void
  type?: 'text' | 'number'
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-sm font-medium text-foreground">
          {label}
        </span>
        {desc ? (
          <span className="text-xs text-muted-foreground">
            {desc}
          </span>
        ) : null}
      </div>
      <Input
        type={type}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-20 h-9 px-2 text-center font-mono text-sm bg-[var(--nw-glass-bg)] border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
      />
    </div>
  )
}
