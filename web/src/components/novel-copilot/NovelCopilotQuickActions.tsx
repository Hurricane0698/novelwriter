import { ArrowUpRight } from 'lucide-react'
import type { CopilotQuickActionSpec } from './novelCopilotWorkbench'

export function NovelCopilotQuickActions({ actions, onAction, disabled = false }: {
  actions: CopilotQuickActionSpec[]
  onAction: (action: string) => void
  disabled?: boolean
}) {
  return (
    <div className="mt-5 divide-y divide-[var(--nw-copilot-border)]">
      {actions.map((action) => (
        <button key={action.id} type="button" onClick={() => onAction(action.id)} disabled={disabled}
          className="group flex w-full items-start gap-3 px-2 py-3.5 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50">
          <action.icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] font-medium text-foreground">{action.label}</span>
            <span className="mt-1 block text-xs leading-5 text-muted-foreground">{action.description}</span>
          </span>
          <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
        </button>
      ))}
    </div>
  )
}
