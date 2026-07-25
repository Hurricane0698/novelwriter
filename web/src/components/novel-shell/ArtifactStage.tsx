import type { ReactNode } from 'react'
import { NOVEL_SHELL_GLASS_PANEL } from '@/components/novel-shell/panelRecipe'
import { cn } from '@/lib/utils'

export function ArtifactStage({
  children,
  className,
  variant = 'plain',
}: {
  children: ReactNode
  className?: string
  variant?: 'plain' | 'glass'
}) {
  return (
    <section
      className={cn(
        'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden',
        variant === 'glass' && NOVEL_SHELL_GLASS_PANEL,
        className,
      )}
    >
      {children}
    </section>
  )
}
