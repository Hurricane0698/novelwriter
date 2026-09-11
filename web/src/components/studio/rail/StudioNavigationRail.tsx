import '@/lib/uiMessagePacks/novel'
import { BookOpen, X } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { Input } from '@/components/ui/input'
import {
  StudioChapterList,
  type StudioChapterListItem,
} from './StudioChapterList'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'

export function StudioNavigationRail({
  novelTitle,
  searchQuery,
  onSearchQueryChange,
  chapters,
  selectedChapterNumber,
  onSelectChapter,
  chapterCount,
  onCreateChapter,
  isCreating,
  onClose,
  activeStage,
}: {
  novelTitle: string
  searchQuery: string
  onSearchQueryChange: (next: string) => void
  chapters: StudioChapterListItem[]
  selectedChapterNumber: number | null
  onSelectChapter: (chapterNumber: number) => void
  chapterCount: number
  onCreateChapter?: () => void
  isCreating?: boolean
  onClose: () => void
  activeStage: NovelShellStage | null
}) {
  const { t } = useUiLocale()
  const hasSearch = searchQuery.trim().length > 0

  return (
    <div className="flex h-full min-h-0 flex-col text-foreground/90" data-testid="studio-rail">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-4 py-4">
        <div className="mb-4 flex items-center gap-2" title={novelTitle}>
          <BookOpen size={16} className="shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1 truncate text-sm font-medium">{novelTitle}</div>
          <button type="button" onClick={onClose} aria-label={t('studio.layout.closeChapters')}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-foreground/5"><X size={15} /></button>
        </div>

        <Input
          type="text"
          placeholder={t('studio.rail.searchChapters')}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          className="h-8 rounded-md border-border/60 bg-transparent text-[13px] placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="studio-rail-search"
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 px-2 py-3">
        {hasSearch ? (
          <div className="px-2 text-[11px] text-muted-foreground">
            {t('studio.rail.searchResults', { count: chapters.length })}
          </div>
        ) : null}

        <StudioChapterList
          chapters={chapters}
          selectedChapterNumber={selectedChapterNumber}
          onSelectChapter={onSelectChapter}
          chapterCount={chapterCount}
          onCreateChapter={onCreateChapter}
          isCreating={isCreating}
          activeStage={activeStage}
        />
      </div>
    </div>
  )
}
