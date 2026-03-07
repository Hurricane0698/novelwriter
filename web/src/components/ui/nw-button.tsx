import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const nwButtonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--background))] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        accent:
          'bg-accent text-accent-foreground shadow-[0_0_18px_hsl(var(--accent)/0.25)] hover:bg-[hsl(var(--nw-accent-hover))]',
        glass:
          'border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] text-foreground backdrop-blur-xl hover:bg-[var(--nw-glass-bg-hover)] hover:border-[var(--nw-glass-border-hover)]',
        accentOutline:
          'border border-[hsl(var(--accent)/0.35)] bg-[hsl(var(--accent)/0.12)] text-accent hover:bg-[hsl(var(--accent)/0.18)]',
        dangerOutline:
          'border border-[hsl(var(--color-danger)/0.35)] text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)]',
        dangerSoft:
          'border border-[var(--nw-glass-border)] text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.10)]',
        ghost:
          'text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground',
      },
    },
    defaultVariants: {
      variant: 'glass',
    },
  }
)

export interface NwButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof nwButtonVariants> {
  asChild?: boolean
}

export const NwButton = React.forwardRef<HTMLButtonElement, NwButtonProps>(
  ({ className, variant, asChild, type, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        // Default to `button` to avoid accidental form submits.
        type={asChild ? undefined : (type ?? 'button')}
        className={cn(nwButtonVariants({ variant }), className)}
        {...props}
      />
    )
  }
)
NwButton.displayName = 'NwButton'
