import '@/lib/uiMessagePacks/novel'
import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type ComponentProps, type KeyboardEvent } from 'react'
import { FileText, Plus } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { NwButton } from '@/components/ui/nw-button'
import { cn } from '@/lib/utils'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'
import { chapterWindow, DEFAULT_VIEWPORT_HEIGHT, restoreChapterAnchor, ROW_HEIGHT, ROW_STRIDE, shouldRevealChapter } from './chapterWindow'

export type StudioChapterListItem = {
  chapterNumber: number
  label: string
}

const WINDOW_THRESHOLD = 100

function ChapterButton({
  chapter,
  selected,
  onSelectChapter,
  className,
  ...buttonProps
}: ComponentProps<'button'> & {
  chapter: StudioChapterListItem
  selected: boolean
  onSelectChapter: (chapterNumber: number) => void
}) {
  return (
    <button
      {...buttonProps}
      type="button"
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelectChapter(chapter.chapterNumber)}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-[12px] border px-3 py-2 text-left text-[13px] transition-all',
        selected
          ? 'border-accent/25 bg-accent/10 text-accent shadow-sm'
          : 'border-transparent text-foreground/80 hover:bg-foreground/5 hover:text-foreground',
        className,
      )}
    >
      <FileText size={14} className={cn('shrink-0', selected ? 'opacity-100' : 'opacity-55')} />
      <span className="truncate">{chapter.label}</span>
    </button>
  )
}

function WindowedChapterRows({ chapters, selectedChapterNumber, isChapterStage, onSelectChapter }: {
  chapters: StudioChapterListItem[]
  selectedChapterNumber: number | null
  isChapterStage: boolean
  onSelectChapter: (chapterNumber: number) => void
}) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const buttonsRef = useRef(new Map<number, HTMLButtonElement>())
  const pendingFocusRef = useRef<number | null>(null)
  const previousRef = useRef<{ selection: number | null; chapters: StudioChapterListItem[] } | null>(null)
  const anchorRef = useRef({ index: 0, offset: 0 })
  const [focusedChapter, setFocusedChapter] = useState<number | null>(null)
  const [tabStop, setTabStop] = useState<{ selection: number | null; chapter: number } | null>(null)
  const chapterIndices = useMemo(() => new Map(chapters.map((chapter, index) => [chapter.chapterNumber, index])), [chapters])
  const selectedIndex = chapterIndices.get(selectedChapterNumber ?? -1) ?? 0
  const tabStopIndex = tabStop?.selection === selectedChapterNumber
    ? chapterIndices.get(tabStop.chapter) ?? selectedIndex
    : selectedIndex
  const focusedIndex = chapterIndices.get(focusedChapter ?? -1)
  const [window, setWindow] = useState(() => chapterWindow(chapters.length, 0, DEFAULT_VIEWPORT_HEIGHT))

  const syncWindow = useCallback((viewport: HTMLDivElement) => {
    const height = viewport.clientHeight || DEFAULT_VIEWPORT_HEIGHT
    const { start, end } = chapterWindow(chapters.length, viewport.scrollTop, height)
    anchorRef.current = { index: Math.floor(viewport.scrollTop / ROW_STRIDE), offset: viewport.scrollTop % ROW_STRIDE }
    setWindow(previous => previous.start === start && previous.end === end ? previous : { start, end })
  }, [chapters.length])

  const revealChapter = useCallback((index: number) => {
    const viewport = viewportRef.current
    if (!viewport) return
    const height = viewport.clientHeight || DEFAULT_VIEWPORT_HEIGHT
    const top = index * ROW_STRIDE
    if (top < viewport.scrollTop) viewport.scrollTop = top
    else if (top + ROW_HEIGHT > viewport.scrollTop + height) viewport.scrollTop = top + ROW_HEIGHT - height
    syncWindow(viewport)
  }, [syncWindow])

  useLayoutEffect(() => {
    const previous = previousRef.current
    const viewport = viewportRef.current
    if (shouldRevealChapter(previous, selectedChapterNumber)) {
      revealChapter(selectedIndex)
    } else if (viewport && previous) {
      if (previous.chapters !== chapters) {
        const top = restoreChapterAnchor(previous.chapters, chapterIndices, anchorRef.current)
        const maxTop = Math.max(0, chapters.length * ROW_STRIDE - 4 - (viewport.clientHeight || DEFAULT_VIEWPORT_HEIGHT))
        viewport.scrollTop = Math.min(top, maxTop)
      }
      syncWindow(viewport)
    }
    previousRef.current = { selection: selectedChapterNumber, chapters }
  }, [chapterIndices, chapters, revealChapter, selectedChapterNumber, selectedIndex, syncWindow])

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => syncWindow(viewport))
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [syncWindow])

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.altKey || event.metaKey) return
    const pageSize = Math.max(1, Math.floor((viewportRef.current?.clientHeight || DEFAULT_VIEWPORT_HEIGHT) / ROW_STRIDE))
    let target: number
    switch (event.key) {
      case 'ArrowDown': target = index + 1; break
      case 'ArrowUp': target = index - 1; break
      case 'PageDown': target = index + pageSize; break
      case 'PageUp': target = index - pageSize; break
      case 'Home': target = 0; break
      case 'End': target = chapters.length - 1; break
      case 'Tab':
        target = index + (event.shiftKey ? -1 : 1)
        // At the ends, native Tab moves to controls outside the list.
        if (target < 0 || target >= chapters.length) return
        break
      default: return
    }
    event.preventDefault()
    target = Math.max(0, Math.min(chapters.length - 1, target))
    const chapterNumber = chapters[target].chapterNumber
    pendingFocusRef.current = chapterNumber
    revealChapter(target)
    const button = buttonsRef.current.get(chapterNumber)
    if (button) {
      pendingFocusRef.current = null
      button.focus({ preventScroll: true })
    }
  }

  const indices = Array.from({ length: Math.max(0, window.end - window.start) }, (_, offset) => window.start + offset)
    .filter(index => index < chapters.length)
  // A scroll must not remove the focused control or the list's keyboard entry point.
  for (const index of [focusedIndex, tabStopIndex]) {
    if (index !== undefined && !indices.includes(index)) indices.push(index)
  }
  indices.sort((left, right) => left - right)

  return (
    <div
      ref={viewportRef}
      className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto"
      data-testid="studio-chapter-viewport"
      style={{ overflowAnchor: 'none' }}
      onScroll={event => syncWindow(event.currentTarget)}
    >
      <div role="list" className="relative" style={{ height: chapters.length * ROW_STRIDE - 4 }}>
        {indices.map(index => {
          const chapter = chapters[index]
          return (
            <div
              key={chapter.chapterNumber}
              role="listitem"
              aria-setsize={chapters.length}
              aria-posinset={index + 1}
              className="absolute inset-x-0"
              style={{ top: index * ROW_STRIDE, height: ROW_HEIGHT }}
            >
              <ChapterButton
                chapter={chapter}
                selected={isChapterStage && chapter.chapterNumber === selectedChapterNumber}
                onSelectChapter={onSelectChapter}
                className="h-full"
                tabIndex={index === tabStopIndex ? 0 : -1}
                ref={button => {
                  if (!button) {
                    buttonsRef.current.delete(chapter.chapterNumber)
                    return
                  }
                  buttonsRef.current.set(chapter.chapterNumber, button)
                  if (pendingFocusRef.current === chapter.chapterNumber) {
                    pendingFocusRef.current = null
                    button.focus({ preventScroll: true })
                  }
                }}
                onFocus={() => {
                  setFocusedChapter(chapter.chapterNumber)
                  setTabStop({ selection: selectedChapterNumber, chapter: chapter.chapterNumber })
                }}
                onBlur={() => setFocusedChapter(null)}
                onKeyDown={event => handleKeyDown(event, index)}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

export const StudioChapterList = memo(function StudioChapterList({
  chapters,
  selectedChapterNumber,
  onSelectChapter,
  chapterCount,
  onCreateChapter,
  isCreating,
  activeStage,
}: {
  chapters: StudioChapterListItem[]
  selectedChapterNumber: number | null
  onSelectChapter: (chapterNumber: number) => void
  chapterCount: number
  onCreateChapter?: () => void
  isCreating?: boolean
  activeStage: NovelShellStage | null
}) {
  const { t } = useUiLocale()
  const isChapterStage = activeStage !== 'write'

  return (
    <section className="flex min-h-0 flex-1 flex-col" data-testid="studio-rail-chapters">
      <div className="mb-2 flex items-center justify-between px-2">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {t('studio.rail.chapters')}
        </div>
        {onCreateChapter ? (
          <NwButton
            onClick={onCreateChapter}
            disabled={isCreating}
            variant="ghost"
            className="h-6 w-6 rounded-md p-0 text-muted-foreground hover:bg-foreground/5"
            title={t('studio.rail.createChapter')}
          >
            <Plus size={12} />
          </NwButton>
        ) : null}
      </div>

      {chapters.length === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-muted-foreground">
          {t('studio.rail.noChapters')}
        </div>
      ) : chapters.length > WINDOW_THRESHOLD ? (
        <WindowedChapterRows
          chapters={chapters}
          selectedChapterNumber={selectedChapterNumber}
          isChapterStage={isChapterStage}
          onSelectChapter={onSelectChapter}
        />
      ) : (
        <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-1">
            {chapters.map(chapter => (
              <ChapterButton
                key={chapter.chapterNumber}
                chapter={chapter}
                selected={isChapterStage && chapter.chapterNumber === selectedChapterNumber}
                onSelectChapter={onSelectChapter}
              />
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 border-t border-[var(--nw-glass-border)] px-2 pt-3 text-xs text-muted-foreground">
        {t('studio.rail.chapterCount', { count: chapterCount })}
      </div>
    </section>
  )
})
