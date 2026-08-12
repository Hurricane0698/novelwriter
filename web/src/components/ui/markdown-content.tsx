import { Children, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { AnnotatedText, type TextAnnotation } from '@/components/ui/annotated-text'
import { cn } from '@/lib/utils'

function annotatedChildren(children: ReactNode, annotations: TextAnnotation[]) {
  return Children.map(children, (child) => (
    typeof child === 'string'
      ? <AnnotatedText text={child} annotations={annotations} />
      : child
  ))
}
function isSafeLink(href: string | undefined): href is string {
  if (!href) return false
  if (href.startsWith('/') || href.startsWith('#')) return true
  try {
    return ['http:', 'https:', 'mailto:'].includes(new URL(href).protocol)
  } catch {
    return false
  }
}

function markdownComponents(annotations: TextAnnotation[]): Components {
  return {
    h1: ({ children }) => <h1 className="mb-5 mt-8 text-3xl font-semibold tracking-tight">{annotatedChildren(children, annotations)}</h1>,
    h2: ({ children }) => <h2 className="mb-4 mt-7 text-2xl font-semibold tracking-tight">{annotatedChildren(children, annotations)}</h2>,
    h3: ({ children }) => <h3 className="mb-3 mt-6 text-xl font-semibold">{annotatedChildren(children, annotations)}</h3>,
    h4: ({ children }) => <h4 className="mb-3 mt-5 text-lg font-semibold">{annotatedChildren(children, annotations)}</h4>,
    h5: ({ children }) => <h5 className="mb-2 mt-4 text-base font-semibold">{annotatedChildren(children, annotations)}</h5>,
    h6: ({ children }) => <h6 className="mb-2 mt-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{annotatedChildren(children, annotations)}</h6>,
    p: ({ children }) => <p className="my-4 text-[15px] leading-[2] text-foreground">{annotatedChildren(children, annotations)}</p>,
    strong: ({ children }) => <strong className="font-semibold text-foreground">{annotatedChildren(children, annotations)}</strong>,
    em: ({ children }) => <em>{annotatedChildren(children, annotations)}</em>,
    ul: ({ children }) => <ul className="my-4 list-disc space-y-2 pl-6">{children}</ul>,
    ol: ({ children }) => <ol className="my-4 list-decimal space-y-2 pl-6">{children}</ol>,
    li: ({ children }) => <li className="pl-1 text-[15px] leading-7">{annotatedChildren(children, annotations)}</li>,
    blockquote: ({ children }) => (
      <blockquote className="my-5 border-l-2 border-[hsl(var(--accent)/0.55)] pl-5 text-muted-foreground">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-8 border-[var(--nw-glass-border)]" />,
    pre: ({ children }) => <pre className="my-5 overflow-x-auto rounded-xl border border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.05)] p-4 text-sm leading-6">{children}</pre>,
    code: ({ children, className }) => (
      <code className={cn('rounded bg-[hsl(var(--foreground)/0.06)] px-1.5 py-0.5 font-mono text-[0.9em]', className)}>
        {annotatedChildren(children, annotations)}
      </code>
    ),
    a: ({ href, children }) => (
      isSafeLink(href)
        ? <a href={href} rel="noreferrer" className="text-accent underline underline-offset-4">{annotatedChildren(children, annotations)}</a>
        : <span>{annotatedChildren(children, annotations)}</span>
    ),
    img: ({ alt }) => (
      alt ? <span className="text-sm text-muted-foreground">[{alt}]</span> : null
    ),
  }
}

export function MarkdownContent({
  isLoading,
  content,
  loadingLabel,
  emptyLabel,
  annotations = [],
  maxWidth = false,
  className,
}: {
  isLoading?: boolean
  content: string | null | undefined
  loadingLabel?: string
  emptyLabel?: string
  annotations?: TextAnnotation[]
  maxWidth?: boolean
  className?: string
}) {
  const { t } = useUiLocale()
  if (isLoading) {
    return <div className={cn('flex h-full items-center justify-center text-sm text-muted-foreground', className)}>{loadingLabel ?? t('plainText.loading')}</div>
  }
  if (!(content ?? '').trim()) {
    return <div className={cn('flex h-full items-center justify-center text-sm text-muted-foreground', className)}>{emptyLabel ?? t('plainText.empty')}</div>
  }

  return (
    <div className={cn(maxWidth && 'mx-auto max-w-3xl', className)} data-testid="markdown-content">
      <ReactMarkdown components={markdownComponents(annotations)} skipHtml>
        {content ?? ''}
      </ReactMarkdown>
    </div>
  )
}
