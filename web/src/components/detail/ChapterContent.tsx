import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import type { TextAnnotation } from '@/components/ui/annotated-text'
import { MarkdownContent } from '@/components/ui/markdown-content'
import { isMarkdownContentFormat } from '@/lib/novelContentFormat'
import type { NovelContentFormat } from '@/types/api'

export function ChapterContent({
  isLoading,
  content,
  contentFormat,
  annotations,
}: {
  isLoading: boolean
  content: string | null
  contentFormat: NovelContentFormat
  annotations?: TextAnnotation[]
}) {
  const { t } = useUiLocale()
  const isMarkdown = isMarkdownContentFormat(contentFormat)

  return (
    <GlassCard className="flex-1 overflow-auto rounded-xl p-6 sm:p-8 nw-scrollbar-thin">
      {isMarkdown ? (
        <MarkdownContent
          isLoading={isLoading}
          content={content}
          loadingLabel={t('chapter.loadingContent')}
          emptyLabel={t('chapter.emptySelectToRead')}
          maxWidth
          annotations={annotations}
        />
      ) : (
        <PlainTextContent
          isLoading={isLoading}
          content={content}
          loadingLabel={t('chapter.loadingContent')}
          emptyLabel={t('chapter.emptySelectToRead')}
          maxWidth
          contentClassName="space-y-6"
          annotations={annotations}
        />
      )}
    </GlassCard>
  )
}
