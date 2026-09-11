import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function AiStatusPill({ status }: { status: 'idle' | 'running' | 'error' }) {
  const { t } = useUiLocale()
  return (
    <span role="status" className={cn('inline-flex shrink-0 items-center gap-1.5 text-[11px]', status === 'error' ? 'text-[hsl(var(--color-danger))]' : 'text-muted-foreground')}>
      <span className={cn('h-1.5 w-1.5 rounded-full bg-current', status === 'running' && 'motion-safe:animate-pulse')} />
      {t(status === 'running' ? 'copilot.aiStatus.running' : status === 'error' ? 'copilot.aiStatus.error' : 'copilot.aiStatus.idle')}
    </span>
  )
}
