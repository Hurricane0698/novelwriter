import { Loader2 } from 'lucide-react'
import { ProseWarningsPanel } from '@/components/generation/ProseWarningsPanel'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import { MarkdownContent } from '@/components/ui/markdown-content'
import type { TextAnnotation } from '@/components/ui/annotated-text'
import { NwButton } from '@/components/ui/nw-button'
import { isMarkdownContentFormat } from '@/lib/novelContentFormat'
import type { Continuation, NovelContentFormat, ProseWarning } from '@/types/api'
import type { ContinuationResultsT, VariantState } from './helpers'

interface ContinuationResultsPaneProps {
  contentFormat: NovelContentFormat
  isStreamMode: boolean
  isFallbackMode: boolean
  currentVariant?: VariantState
  currentLegacyVersion?: Continuation
  driftAnnotations: TextAnnotation[]
  proseWarnings: ProseWarning[]
  onRetryStream: () => void
  t: ContinuationResultsT
}

function ContinuationResultContent({
  content,
  contentFormat,
  emptyLabel,
  annotations,
}: {
  content: string | null | undefined
  contentFormat: NovelContentFormat
  emptyLabel: string
  annotations?: TextAnnotation[]
}) {
  const className = 'flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin'
  if (isMarkdownContentFormat(contentFormat)) {
    return (
      <MarkdownContent
        content={content}
        className={className}
        emptyLabel={emptyLabel}
        annotations={annotations}
      />
    )
  }
  return (
    <PlainTextContent
      content={content}
      className={className}
      emptyLabel={emptyLabel}
      annotations={annotations}
    />
  )
}

export function ContinuationResultsPane({
  contentFormat,
  isStreamMode,
  isFallbackMode,
  currentVariant,
  currentLegacyVersion,
  driftAnnotations,
  proseWarnings,
  onRetryStream,
  t,
}: ContinuationResultsPaneProps) {
  return (
    <>
      {isStreamMode && !isFallbackMode ? (
        !currentVariant ? (
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        ) : currentVariant.error ? (
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <span className="text-sm text-destructive">{currentVariant.error}</span>
              <NwButton
                onClick={onRetryStream}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                {t('continuation.results.retry')}
              </NwButton>
            </div>
          </div>
        ) : currentVariant.content ? (
          <ContinuationResultContent
            content={currentVariant.content}
            contentFormat={contentFormat}
            emptyLabel={t('continuation.results.emptyContent')}
            annotations={driftAnnotations}
          />
        ) : currentVariant.isStreaming || !currentVariant.continuationId ? (
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        ) : (
          <ContinuationResultContent
            content=""
            contentFormat={contentFormat}
            emptyLabel={t('continuation.results.emptyContent')}
          />
        )
      ) : (
        <ContinuationResultContent
          content={currentLegacyVersion?.content}
          contentFormat={contentFormat}
          emptyLabel={t('continuation.results.emptyContent')}
          annotations={driftAnnotations}
        />
      )}

      {proseWarnings.length > 0 ? (
        <ProseWarningsPanel warnings={proseWarnings} />
      ) : null}
    </>
  )
}
