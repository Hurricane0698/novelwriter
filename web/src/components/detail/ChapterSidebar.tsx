import { Plus } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { NwButton } from '@/components/ui/nw-button'
import { cn } from '@/lib/utils'

export type ChapterSidebarItem = {
  chapterNumber: number
  label: string
}

export function ChapterSidebar({
  novelTitle,
  searchQuery,
  onSearchQueryChange,
  chapters,
  selectedChapterNumber,
  onSelectChapter,
  chapterCount,
  onCreateChapter,
  isCreating,
}: {
  novelTitle: string
  searchQuery: string
  onSearchQueryChange: (next: string) => void
  chapters: ChapterSidebarItem[]
  selectedChapterNumber: number | null
  onSelectChapter: (chapterNumber: number) => void
  chapterCount: number
  onCreateChapter: () => void
  isCreating: boolean
}) {
  return (
    <aside className="w-[280px] shrink-0 flex flex-col min-h-0 h-full border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl">
      <div className="p-4 border-b border-[var(--nw-glass-border)]">
        <div
          className="font-mono text-base font-semibold text-foreground truncate"
          title={novelTitle}
        >
          {novelTitle}
        </div>

        <div className="mt-3">
          <Input
            type="text"
            placeholder="搜索章节..."
            value={searchQuery}
            onChange={e => onSearchQueryChange(e.target.value)}
            className="h-9 text-sm bg-[var(--nw-glass-bg)] border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2 nw-scrollbar-thin">
        {chapters.length === 0 ? (
          <div className="px-5 py-6 text-sm text-muted-foreground text-center">
            {searchQuery.trim() ? '无匹配章节' : '暂无章节'}
          </div>
        ) : chapters.map((c) => {
          const selected = c.chapterNumber === selectedChapterNumber
          return (
            <button
              key={c.chapterNumber}
              type="button"
              onClick={() => onSelectChapter(c.chapterNumber)}
              className={cn(
                'w-full text-left px-5 py-2 text-sm transition-colors',
                selected
                  ? 'bg-[hsl(var(--accent)/0.10)] border-l-2 border-l-accent text-accent font-medium'
                  : 'text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)]'
              )}
            >
              {c.label}
            </button>
          )
        })}
      </div>

      <div className="relative">
        <div className="pointer-events-none absolute top-[-32px] left-0 right-0 h-8 bg-gradient-to-b from-transparent to-[hsl(var(--background))]" />
        <div className="flex items-center justify-between px-4 py-2 border-t border-[var(--nw-glass-border)]">
          <span className="text-[10px] text-muted-foreground">
            共 {chapterCount} 章
          </span>
          <NwButton
            onClick={onCreateChapter}
            disabled={isCreating}
            variant="glass"
            className="w-6 h-6 rounded-md disabled:opacity-50"
            title="新建章节"
          >
            <Plus size={12} className="text-muted-foreground" />
          </NwButton>
        </div>
      </div>
    </aside>
  )
}
