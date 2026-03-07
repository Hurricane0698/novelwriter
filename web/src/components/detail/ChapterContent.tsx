import { GlassCard } from '@/components/GlassCard'
import { PlainTextContent } from '@/components/ui/plain-text-content'

export function ChapterContent({
  isLoading,
  content,
}: {
  isLoading: boolean
  content: string | null
}) {
  return (
    <GlassCard className="flex-1 overflow-auto rounded-xl p-6 sm:p-8 nw-scrollbar-thin">
      <PlainTextContent
        isLoading={isLoading}
        content={content}
        loadingLabel="加载章节内容..."
        emptyLabel="选择一个章节开始阅读"
        maxWidth
        contentClassName="space-y-6"
      />
    </GlassCard>
  )
}
