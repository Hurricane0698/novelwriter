import { Loader2 } from 'lucide-react'
import { NwButton } from '@/components/ui/nw-button'
import type { ContinuationResultsT } from './helpers'

export function ContinuationResultsLoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center flex-col gap-4">
      <Loader2 size={24} className="animate-spin text-muted-foreground" />
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  )
}

interface ContinuationResultsReloadErrorStateProps {
  error: string
  onRetry: () => void
  onBack: () => void
  t: ContinuationResultsT
}

export function ContinuationResultsReloadErrorState({ error, onRetry, onBack, t }: ContinuationResultsReloadErrorStateProps) {
  return (
    <div className="flex flex-1 items-center justify-center flex-col gap-4">
      <span className="text-sm text-destructive">{error}</span>
      <div className="flex items-center gap-3">
        <NwButton
          onClick={onRetry}
          variant="accent"
          className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
        >
          {t('continuation.results.retry')}
        </NwButton>
        <NwButton
          onClick={onBack}
          variant="glass"
          className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
        >
          {t('continuation.results.back')}
        </NwButton>
      </div>
    </div>
  )
}

interface ContinuationResultsEmptyStateProps {
  onBack: () => void
  t: ContinuationResultsT
}

export function ContinuationResultsEmptyState({ onBack, t }: ContinuationResultsEmptyStateProps) {
  return (
    <div className="flex flex-1 items-center justify-center flex-col gap-4">
      <span className="text-sm text-muted-foreground">{t('continuation.results.noResults')}</span>
      <NwButton
        onClick={onBack}
        variant="accent"
        className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
      >
        {t('continuation.results.returnToWorkspace')}
      </NwButton>
    </div>
  )
}
