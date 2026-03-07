import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

/**
 * Token-driven glass surface wrapper.
 *
 * Goal: keep "glass recipe" centralized (fill/border/blur/shadow) while letting
 * callers control layout (padding, rounding, borders on specific sides, etc).
 */
const glassSurfaceVariants = cva('border-[var(--nw-glass-border)] text-foreground', {
  variants: {
    variant: {
      /**
       * Large surfaces like cards / panels / sidebars.
       * Uses glass tokens + strong blur. Shadow is intentionally omitted by default.
       */
      container: 'bg-[var(--nw-glass-bg)] backdrop-blur-[20px]',
      /**
       * Inputs / inline controls.
       * No blur to avoid "double blur" inside container surfaces.
       */
      control: 'bg-[var(--nw-glass-bg)]',
      /**
       * Dropdowns / popovers / toasts / bottom sheets.
       * More opaque base for readability + deeper shadow for separation.
       */
      floating:
        'bg-[hsl(var(--background)/0.75)] backdrop-blur-[20px] shadow-[0_18px_50px_rgba(0,0,0,0.55)]',
    },
    bordered: {
      true: 'border',
      false: 'border-0',
    },
    hoverable: {
      true: 'transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:border-[var(--nw-glass-border-hover)]',
      false: null,
    },
  },
  defaultVariants: {
    variant: 'container',
    bordered: true,
    hoverable: false,
  },
})

export type GlassSurfaceVariant = NonNullable<VariantProps<typeof glassSurfaceVariants>['variant']>

export interface GlassSurfaceProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof glassSurfaceVariants> {
  asChild?: boolean
}

export const GlassSurface = React.forwardRef<HTMLDivElement, GlassSurfaceProps>(
  ({ className, variant, bordered, hoverable, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : 'div'
    return (
      <Comp
        ref={ref}
        className={cn(glassSurfaceVariants({ variant, bordered, hoverable }), className)}
        {...props}
      />
    )
  }
)
GlassSurface.displayName = 'GlassSurface'
