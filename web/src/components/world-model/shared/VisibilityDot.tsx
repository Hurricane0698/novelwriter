import { cn } from '@/lib/utils'
import type { Visibility } from '@/types/api'

const CYCLE: Visibility[] = ['active', 'reference', 'hidden']

const VIS_VARS: Record<Visibility, { varName: string; label: string }> = {
  active: { varName: '--color-vis-active', label: 'active' },
  reference: { varName: '--color-vis-reference', label: 'reference' },
  hidden: { varName: '--color-vis-hidden', label: 'hidden' },
}

const FILL_CLIP: Record<Visibility, string> = {
  // Full, half, hollow (no fill). Clip-path animates smoothly between these.
  active: 'inset(0% 0% 0% 0%)',
  reference: 'inset(0% 50% 0% 0%)',
  hidden: 'inset(0% 100% 0% 0%)',
}

export function VisibilityDot({ visibility, onChange, className }: {
  visibility: Visibility
  onChange: (v: Visibility) => void
  className?: string
}) {
  const next = CYCLE[(CYCLE.indexOf(visibility) + 1) % CYCLE.length]
  const { varName, label } = VIS_VARS[visibility]
  const nextLabel = VIS_VARS[next].label
  const ringAlpha = visibility === 'hidden' ? 0.28 : 0.48
  const glowAlpha = visibility === 'active' ? 0.6 : visibility === 'reference' ? 0.38 : 0.14

  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center shrink-0 rounded-full p-0.5',
        'transition-transform duration-150 hover:scale-[1.04] active:scale-[0.98]',
        className,
      )}
      data-testid="visibility-dot"
      data-visibility={visibility}
      onClick={e => { e.stopPropagation(); onChange(next) }}
      onPointerDown={e => e.stopPropagation()}
      aria-label={`Visibility: ${label}. Click to set ${nextLabel}.`}
      title={`Visibility: ${label}`}
    >
      <span
        className="relative block h-2.5 w-2.5 overflow-hidden rounded-full border transition-[box-shadow,border-color,transform] duration-200"
        style={{
          borderColor: `hsl(var(${varName}) / ${ringAlpha})`,
          boxShadow: [
            `0 0 10px hsl(var(${varName}) / ${glowAlpha})`,
            `0 0 0 0.5px hsl(var(${varName}) / 0.16) inset`,
          ].join(', '),
        }}
      >
        <span
          className="absolute inset-0 rounded-full transition-[clip-path,opacity,background] duration-200"
          style={{
            clipPath: FILL_CLIP[visibility],
            // Full/half/hollow semantics: fill morphs; ring/glow still show in hollow state.
            opacity: visibility === 'hidden' ? 0 : 1,
            background: [
              // Glass-texture fill: subtle highlight + tinted glow.
              'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.55), rgba(255,255,255,0) 55%)',
              `radial-gradient(circle at 60% 70%, hsl(var(${varName}) / 0.55), hsl(var(${varName}) / 0.18) 70%)`,
            ].join(', '),
          }}
        />
        <span
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.35), rgba(255,255,255,0) 62%)',
          }}
        />
      </span>
    </button>
  )
}
