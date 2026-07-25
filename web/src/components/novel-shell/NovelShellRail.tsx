import type { ReactNode } from 'react'
import { NOVEL_SHELL_GLASS_PANEL } from '@/components/novel-shell/panelRecipe'
import { cn } from '@/lib/utils'

export function NovelShellRail({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <aside
      className={cn(
        'flex h-full min-h-0 shrink-0 flex-col overflow-hidden',
        NOVEL_SHELL_GLASS_PANEL,
        className,
      )}
    >
      {children}
    </aside>
  )
}
