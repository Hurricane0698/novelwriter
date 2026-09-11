import { useState } from 'react'
import { Check, X, ChevronDown, ChevronUp, Navigation2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { CopilotSuggestion, CopilotSuggestionTarget } from '@/types/copilot'
import { getCopilotSuggestionKindMeta } from './novelCopilotView'
import {
  copilotPillClassName,
  copilotPillInteractiveClassName,
} from './novelCopilotChrome'

export function NovelCopilotSuggestionCard({
  suggestion,
  mode = 'pending',
  isApplying = false,
  onApply,
  onDismiss,
  onLocateTarget,
}: {
  suggestion: CopilotSuggestion
  mode?: 'pending' | 'applied'
  isApplying?: boolean
  onApply: (id: string) => void
  onDismiss: (id: string) => void
  onLocateTarget?: (target: CopilotSuggestionTarget) => void
}) {
  const { locale, t } = useUiLocale()
  const isApplied = mode === 'applied'
  const kindMeta = getCopilotSuggestionKindMeta(suggestion.kind, locale)
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div
      className={cn(
        'group relative border-t border-border/60 py-4',
      )}
      data-testid={`copilot-suggestion-${suggestion.suggestion_id}`}
      data-status={mode}
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.15em]', kindMeta.chipClassName)}>
                {kindMeta.label}
              </span>
              <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-medium text-muted-foreground/80', copilotPillClassName)}>
                {t('copilot.suggestion.evidenceCount', { count: suggestion.evidence_ids.length })}
              </span>
              <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-medium text-muted-foreground/80', copilotPillClassName)}>
                {suggestion.preview.actionable ? t('copilot.suggestion.actionable') : t('copilot.suggestion.referenceOnly')}
              </span>
              {isApplied ? (
                <span className="inline-flex items-center rounded-full border border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.04)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.15em] text-foreground/82">
                  {t('copilot.suggestion.applied')}
                </span>
              ) : null}
            </div>

              <div className="space-y-1.5">
                <h4 className="text-sm font-medium leading-6 text-foreground/95">
                  {suggestion.title}
                </h4>
                <p className="text-[13px] leading-6 text-muted-foreground/85">
                  {suggestion.summary}
                </p>
                {!suggestion.preview.actionable && suggestion.preview.non_actionable_reason ? (
                  <p className="text-[11px] leading-5 text-amber-600/90 dark:text-amber-300/90">
                    {suggestion.preview.non_actionable_reason}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {suggestion.preview.field_deltas.map((delta) => (
                    <span
                      key={`${suggestion.suggestion_id}-${delta.field}`}
                      className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium text-muted-foreground/75',
                      copilotPillClassName,
                    )}
                  >
                    {delta.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {isExpanded && !isApplied && (
          <div className="mt-4 border-t border-[hsl(var(--foreground)/0.08)] pt-4 pb-2 animate-in slide-in-from-top-2 fade-in duration-300">
            <div className="text-[11px] font-semibold text-foreground/80 mb-2 uppercase tracking-wide">
              {t('copilot.suggestion.changePreview')}
            </div>
            <div className="text-xs leading-5 text-muted-foreground">
              <div className="mb-2 pb-2 border-b border-[hsl(var(--foreground)/0.06)]">
                <span className="font-medium text-foreground">{t('copilot.suggestion.target')}</span> {suggestion.preview.target_label}
              </div>
              <div className="mb-3 text-[11px] leading-5 text-muted-foreground/80">
                {suggestion.preview.summary}
              </div>
              <div className="space-y-2">
                {suggestion.preview.field_deltas.map((delta) => (
                  <div key={`${suggestion.suggestion_id}-${delta.field}`} className="border-t border-border/40 py-2.5">
                    <div className="mb-1 text-[11px] font-medium text-foreground">{delta.label}</div>
                    <div className="flex gap-2">
                      <span className="shrink-0 text-[hsl(var(--color-danger))] line-through opacity-70">{t('copilot.suggestion.previousValue')}</span>
                      <span>{delta.before ?? t('copilot.suggestion.emptyValue')}</span>
                    </div>
                    <div className="mt-1 flex gap-2">
                      <span className="shrink-0 font-medium text-[hsl(var(--color-success))]">{t('copilot.suggestion.newValue')}</span>
                      <span className="text-foreground/90">{delta.after}</span>
                    </div>
                  </div>
                ))}
              </div>
              {suggestion.preview.evidence_quotes.length > 0 && (
                <div className="mt-3 border-t border-[hsl(var(--foreground)/0.06)] pt-3">
                  <div className="mb-2 text-[11px] font-medium text-foreground">{t('copilot.suggestion.keyEvidence')}</div>
                  <div className="space-y-2">
                    {suggestion.preview.evidence_quotes.map((quote, index) => (
                      <div key={`${suggestion.suggestion_id}-quote-${index}`} className="border-l-2 border-accent/25 pl-3 py-1 text-[11px] leading-5 text-muted-foreground">
                        {quote}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {isApplied ? (
          <div className="mt-4 flex items-center justify-between gap-2 border-t border-[hsl(var(--foreground)/0.10)] pt-3 text-[11px] text-foreground/72">
            <span>{t('copilot.suggestion.appliedNote')}</span>
            <Check className="h-3.5 w-3.5" />
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[hsl(var(--foreground)/0.08)] pt-3">
            <div className="mr-auto flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium text-muted-foreground hover:bg-[hsl(var(--foreground)/0.05)] hover:text-foreground transition-colors"
              >
                {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {isExpanded ? t('copilot.suggestion.collapsePreview') : t('copilot.suggestion.expandPreview')}
              </button>
            </div>

            {onLocateTarget ? (
              <button
                type="button"
                onClick={() => onLocateTarget(suggestion.target)}
                className={cn(
                  'inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium text-muted-foreground hover:text-foreground',
                  copilotPillInteractiveClassName,
                )}
                aria-label={t('copilot.suggestion.locate')}
              >
                <Navigation2 className="h-3.5 w-3.5" />
                {t('copilot.suggestion.locate')}
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => onDismiss(suggestion.suggestion_id)}
              className={cn(
                'inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium text-muted-foreground hover:text-foreground',
                copilotPillInteractiveClassName,
              )}
              aria-label={t('copilot.suggestion.dismiss')}
            >
              <X className="h-3.5 w-3.5" />
              {t('copilot.suggestion.dismiss')}
            </button>

              <button
                type="button"
                onClick={() => onApply(suggestion.suggestion_id)}
                disabled={isApplying || !suggestion.preview.actionable}
                title={!suggestion.preview.actionable ? (suggestion.preview.non_actionable_reason ?? t('copilot.suggestion.notActionable')) : undefined}
                className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[hsl(var(--foreground)/0.12)] bg-foreground px-4 text-xs font-medium text-background shadow-[0_2px_8px_rgba(0,0,0,0.08)] transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-foreground/90 hover:shadow-[0_6px_16px_rgba(0,0,0,0.12)] hover:-translate-y-[1px] active:scale-[0.97] active:duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--foreground)/0.2)] focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:translate-y-0 disabled:hover:bg-foreground"
              >
                <Check className="h-3.5 w-3.5" /> {isApplying ? t('copilot.suggestion.applying') : t('copilot.suggestion.apply')}
              </button>
            </div>
        )}
      </div>
    </div>
  )
}
