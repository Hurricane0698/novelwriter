import { Check, Loader2, RefreshCw, Upload } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { NwButton } from '@/components/ui/nw-button'
import {
  MARKDOWN_CHAPTER_BODY_INVALID,
  type ChapterMutationErrorCode,
} from '@/lib/chapterMutationError'
import type { ContinuationResultsT } from './helpers'

export type ContinuationAdoptErrorCode = ChapterMutationErrorCode | 'chapter_adopt_failed'

interface ContinuationResultsHeaderProps {
  activeChapterNum: number | null
  activeChapterReference?: string | null
  fallbackNotice: string | null
  isStreamMode: boolean
  isDone: boolean
  currentContent: string
  allDone: boolean
  createPending: boolean
  adoptErrorCode: ContinuationAdoptErrorCode | null
  onAdopt: () => void
  onBackToWrite: () => void
  onExportAll: () => void
  assistOpen?: boolean
  onToggleAssist?: () => void
  t: ContinuationResultsT
}

export function ContinuationResultsHeader({
  activeChapterNum,
  activeChapterReference,
  fallbackNotice,
  isStreamMode,
  isDone,
  currentContent,
  allDone,
  createPending,
  adoptErrorCode,
  onAdopt,
  onBackToWrite,
  onExportAll,
  assistOpen,
  onToggleAssist,
  t,
}: ContinuationResultsHeaderProps) {
  const adoptErrorMessage = adoptErrorCode === null
    ? null
    : adoptErrorCode === MARKDOWN_CHAPTER_BODY_INVALID
      ? t('continuation.results.adoptMarkdownChapterBodyInvalid')
      : t('continuation.results.adoptFailed')

  return (
    <div className="shrink-0 border-b border-[var(--nw-glass-border)] pb-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] font-medium text-foreground/88">
              {t('continuation.results.badge')}
            </span>
            {activeChapterNum !== null ? (
              <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                {t('continuation.results.continuationOf', { chapter: activeChapterReference ?? `Ch. ${activeChapterNum}` })}
              </span>
            ) : null}
            {isStreamMode && !isDone ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[hsl(var(--accent)/0.3)] bg-[hsl(var(--accent)/0.08)] px-2.5 py-1 text-[11px] text-accent">
                <Loader2 size={10} className="animate-spin" />
                {t('continuation.results.generating')}
              </span>
            ) : null}
          </div>
          {fallbackNotice ? (
            <p className="m-0 text-sm text-muted-foreground">{fallbackNotice}</p>
          ) : null}
        </div>

        <div className="flex items-center gap-2.5 flex-wrap justify-end">
          <NwButton
            data-testid="results-adopt-button"
            onClick={onAdopt}
            disabled={createPending || !currentContent || !allDone}
            variant="accent"
            className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)] disabled:cursor-default"
          >
            <Check size={16} />
            {t('continuation.results.adopt')}
          </NwButton>

          <NwButton
            onClick={onBackToWrite}
            variant="glass"
            className="rounded-[10px] px-4 py-2 text-sm font-medium"
          >
            <RefreshCw size={14} />
            {t('continuation.results.regenerate')}
          </NwButton>

          <NwButton
            onClick={onExportAll}
            disabled={!allDone}
            variant="glass"
            className="rounded-[10px] px-4 py-2 text-sm font-medium"
          >
            <Upload size={14} />
            {t('continuation.results.exportAll')}
          </NwButton>

          {onToggleAssist ? <AssistToggleButton active={assistOpen} onClick={onToggleAssist} /> : null}
        </div>
      </div>
      {adoptErrorMessage ? (
        <p
          role="alert"
          data-testid="continuation-adopt-error"
          className="mt-3 rounded-[10px] border border-[hsl(var(--color-danger)/0.25)] bg-[hsl(var(--color-danger)/0.08)] px-3 py-2 text-sm text-[hsl(var(--color-danger))]"
        >
          {adoptErrorMessage}
        </p>
      ) : null}
    </div>
  )
}
