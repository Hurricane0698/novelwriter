import { Bot, Search } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import {
  getCopilotResearchStatusClassName,
} from '@/components/novel-copilot/novelCopilotChrome'
import type { WindowIndexStatusMeta } from '@/lib/windowIndexStatus'
import { cn } from '@/lib/utils'

export interface StudioContextualCopilotAction {
  title: string
  description: string
  onClick: () => void
}

export function StudioResearchPanel({
  indexStatus,
  onOpenWholeBookCopilot,
  contextualCopilotAction,
}: {
  indexStatus: Pick<WindowIndexStatusMeta, 'text' | 'tone'>
  onOpenWholeBookCopilot: () => void
  contextualCopilotAction?: StudioContextualCopilotAction
}) {
  const { t } = useUiLocale()
  const indexStatusClassName = getCopilotResearchStatusClassName(indexStatus.tone)

  return (
    <section className="space-y-1.5" data-testid="studio-research-panel">
      <button
        type="button"
        onClick={onOpenWholeBookCopilot}
        className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
        data-testid="novel-copilot-trigger"
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
          <Search className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-foreground">{t('studio.research.openWholeBook')}</div>
          <div className={cn('mt-0.5 text-[11px]', indexStatusClassName)}>
            {indexStatus.text}
          </div>
        </div>
      </button>

      {contextualCopilotAction ? (
        <button
          type="button"
          onClick={contextualCopilotAction.onClick}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
          data-testid="studio-contextual-copilot-trigger"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
            <Bot className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-foreground">
              {contextualCopilotAction.title}
            </div>
            <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground/80">
              {contextualCopilotAction.description}
            </div>
          </div>
        </button>
      ) : null}
    </section>
  )
}
