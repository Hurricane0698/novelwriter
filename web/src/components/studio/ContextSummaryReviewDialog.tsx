import { useEffect, useRef, useState } from 'react'
import { Check, RefreshCw, Save, X } from 'lucide-react'
import { NwButton } from '@/components/ui/nw-button'
import { Textarea } from '@/components/ui/textarea'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { NovelContextSummary } from '@/types/api'

export function ContextSummaryReviewDialog({
  summary,
  error,
  saving,
  regenerating,
  onClose,
  onSave,
  onRegenerate,
}: {
  summary: NovelContextSummary | null
  error: string | null
  saving: boolean
  regenerating: boolean
  onClose: () => void
  onSave: (
    summaryId: number,
    content: string,
    reviewStatus: NovelContextSummary['review_status'],
  ) => Promise<NovelContextSummary>
  onRegenerate: (summaryId: number) => Promise<NovelContextSummary>
}) {
  const { t } = useUiLocale()
  const [content, setContent] = useState(summary?.content ?? '')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!summary) return
    requestAnimationFrame(() => textareaRef.current?.focus())
  }, [summary])

  useEffect(() => {
    if (!summary) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving && !regenerating) onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose, regenerating, saving, summary])

  if (!summary) return null

  const busy = saving || regenerating
  const contentIsEmpty = content.trim().length === 0
  const statusLabel = summary.is_stale
    ? t('continuation.setup.contextSummary.status.stale')
    : summary.review_status === 'confirmed'
      ? t('continuation.setup.contextSummary.status.confirmed')
      : t('continuation.setup.contextSummary.status.draft')

  const save = async (reviewStatus: NovelContextSummary['review_status']) => {
    if (contentIsEmpty) return
    try {
      await onSave(summary.id, content, reviewStatus)
      if (reviewStatus === 'confirmed') onClose()
    } catch {
      // The parent translates and exposes the structured API error.
    }
  }

  const regenerate = async () => {
    try {
      const updated = await onRegenerate(summary.id)
      setContent(updated.content)
    } catch {
      // The parent translates and exposes the structured API error.
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/55 p-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="context-summary-review-title"
      data-testid="context-summary-review-dialog"
    >
      <div className="flex max-h-[min(780px,90vh)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--nw-glass-border)] bg-background shadow-2xl">
        <div className="flex items-start justify-between border-b border-[var(--nw-glass-border)] px-6 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="context-summary-review-title" className="truncate text-base font-semibold text-foreground">
                {summary.title}
              </h2>
              <span className="rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {statusLabel}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {t('continuation.setup.contextSummary.reviewDescription')}
            </p>
          </div>
          <button
            type="button"
            aria-label={t('continuation.setup.contextSummary.close')}
            onClick={onClose}
            disabled={busy}
            className="ml-4 inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50"
          >
            <X size={15} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-auto px-6 py-5">
          {summary.is_stale ? (
            <div className="rounded-xl border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.10)] px-4 py-3 text-xs leading-5 text-[hsl(var(--color-warning))]">
              {t('continuation.setup.contextSummary.staleDescription')}
            </div>
          ) : null}
          <Textarea
            ref={textareaRef}
            value={content}
            onChange={event => setContent(event.target.value)}
            aria-label={t('continuation.setup.contextSummary.contentLabel')}
            data-testid="context-summary-content"
            className="min-h-[360px] resize-y whitespace-pre-wrap bg-[var(--nw-glass-bg)] text-[13px] leading-6"
          />
          {error ? (
            <p role="alert" className="text-xs leading-5 text-[hsl(var(--color-danger))]">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--nw-glass-border)] px-6 py-4">
          <NwButton
            variant="glass"
            className="h-9 rounded-lg px-3 text-xs"
            disabled={busy}
            onClick={() => void regenerate()}
          >
            <RefreshCw size={13} className={regenerating ? 'animate-spin' : ''} />
            {regenerating
              ? t('continuation.setup.contextSummary.regenerating')
              : t('continuation.setup.contextSummary.regenerate')}
          </NwButton>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <NwButton
              variant="glass"
              className="h-9 rounded-lg px-3 text-xs"
              disabled={busy || contentIsEmpty}
              onClick={() => void save('draft')}
            >
              <Save size={13} />
              {t('continuation.setup.contextSummary.saveDraft')}
            </NwButton>
            <NwButton
              variant="accent"
              className="h-9 rounded-lg px-4 text-xs font-semibold"
              disabled={busy || contentIsEmpty || summary.is_stale}
              onClick={() => void save('confirmed')}
            >
              <Check size={13} />
              {t('continuation.setup.contextSummary.confirmAndUse')}
            </NwButton>
          </div>
        </div>
      </div>
    </div>
  )
}
