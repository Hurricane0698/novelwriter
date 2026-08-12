import type { ReactNode } from 'react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { AnnotatedText, type TextAnnotation } from '@/components/ui/annotated-text'

export type PlainTextSplitMode = 'auto' | 'doubleNewline' | 'newline'

function splitPlainText(content: string, mode: PlainTextSplitMode): string[] {
  const normalized = content.replace(/\r\n?/g, '\n')
  if (!normalized) return []

  if (mode === 'doubleNewline') {
    return normalized.split(/\n{2,}/)
  }
  if (mode === 'newline') {
    // Treat any run of line breaks as a paragraph boundary.
    return normalized.split(/\n+/)
  }

  // auto: prefer paragraph breaks when present, otherwise treat line breaks as paragraphs.
  return normalized.includes('\n\n') ? normalized.split(/\n{2,}/) : normalized.split(/\n+/)
}

/**
 * Apply annotations to a paragraph string.
 *
 * For each annotation term, finds ALL non-overlapping occurrences (greedy left-to-right,
 * longest first for ties at same position) and wraps them in highlight spans.
 */
function annotateParagraph(text: string, annotations: TextAnnotation[]): ReactNode[] {
  return [<AnnotatedText key="annotated" text={text} annotations={annotations} />]
}

export function PlainTextContent({
  isLoading,
  content,
  loadingLabel,
  emptyLabel,
  splitMode = 'newline',
  maxWidth,
  className,
  contentClassName,
  paragraphClassName,
  annotations,
}: {
  isLoading?: boolean
  content: string | null | undefined
  loadingLabel?: string
  emptyLabel?: string
  splitMode?: PlainTextSplitMode
  /** Center text content with a readable max width. */
  maxWidth?: boolean
  /** Root wrapper class. Useful for scroll containers (`flex-1 min-h-0 overflow-y-auto`). */
  className?: string
  /** Inner content wrapper class. Use to tune spacing (`space-y-6`) or width. */
  contentClassName?: string
  /** Paragraph `<p>` class override. */
  paragraphClassName?: string
  /** Optional text annotations. No annotations = current behavior. */
  annotations?: TextAnnotation[]
}) {
  const { t } = useUiLocale()
  const effectiveLoadingLabel = loadingLabel ?? t('plainText.loading')
  const effectiveEmptyLabel = emptyLabel ?? t('plainText.empty')

  if (isLoading) {
    return (
      <div className={cn('h-full flex items-center justify-center', className)}>
        <span className="text-sm text-muted-foreground">{effectiveLoadingLabel}</span>
      </div>
    )
  }

  const raw = content ?? ''
  const paragraphs = splitPlainText(raw, splitMode).filter((p) => p.trim().length > 0)
  if (paragraphs.length === 0) {
    return (
      <div className={cn('h-full flex items-center justify-center', className)}>
        <span className="text-sm text-muted-foreground">{effectiveEmptyLabel}</span>
      </div>
    )
  }

  const hasAnnotations = annotations && annotations.length > 0

  return (
    <div className={cn('h-full', className)}>
      <div
        className={cn(
          'space-y-5',
          maxWidth ? 'max-w-3xl mx-auto' : null,
          contentClassName
        )}
      >
        {paragraphs.map((p, i) => (
          <p
            // Content is already plain text; index keys are stable enough for read-only rendering.
            key={i}
            className={cn('text-[15px] leading-[2] text-foreground', paragraphClassName)}
          >
            {hasAnnotations ? annotateParagraph(p, annotations) : p}
          </p>
        ))}
      </div>
    </div>
  )
}
