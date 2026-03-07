import * as React from 'react'
import { cn } from '@/lib/utils'
import { GlassSurface, type GlassSurfaceVariant } from '@/components/ui/glass-surface'

export type GlassCardVariant = GlassSurfaceVariant

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Visual layering preset.
   * - container: large surfaces (cards/panels/sidebars)
   * - control: inputs/inline controls (no blur)
   * - floating: popovers/menus (deeper shadow)
   */
  variant?: GlassCardVariant
  /** Opt-in hover highlight. */
  hoverable?: boolean
  /** Disable the default 1px border when composing custom borders (e.g. only `border-b`). */
  bordered?: boolean
}

export function GlassCard({
  variant = 'container',
  hoverable,
  bordered,
  className,
  ...props
}: GlassCardProps) {
  const radiusClass = variant === 'container' ? 'rounded-2xl' : 'rounded-xl'
  return (
    <GlassSurface
      variant={variant}
      hoverable={hoverable}
      bordered={bordered}
      className={cn(radiusClass, className)}
      {...props}
    />
  )
}
