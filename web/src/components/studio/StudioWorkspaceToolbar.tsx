import { useState } from 'react'
import { BookOpen, Globe, PanelLeft, PanelRight, PenLine } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'

export function StudioWorkspaceToolbar({ title, onRename, chaptersOpen, onToggleChapters, writing, onToggleWriting,
  canContinue, assistantOpen, onToggleAssistant, onOpenAtlas, onWarmAtlas }: {
  title: string
  onRename: (title: string) => Promise<unknown>
  chaptersOpen: boolean
  onToggleChapters: () => void
  writing: boolean
  onToggleWriting: () => void
  canContinue: boolean
  assistantOpen: boolean
  onToggleAssistant: () => void
  onOpenAtlas: () => void
  onWarmAtlas: () => void
}) {
  const { t } = useUiLocale()
  const [draft, setDraft] = useState<string | null>(null)
  const [renameFailed, setRenameFailed] = useState(false)
  async function saveTitle() {
    const name = draft?.trim()
    if (!name || name === title) { setDraft(null); return }
    try {
      await onRename(name)
      setDraft(null)
      setRenameFailed(false)
    } catch { setRenameFailed(true) }
  }
  const buttonClass = (active = false) => cn('inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-2.5 text-xs transition-colors hover:bg-foreground/5', active ? 'text-accent' : 'text-muted-foreground hover:text-foreground')
  return <header className="flex h-12 shrink-0 items-center gap-1 border-y border-border/50 bg-background px-2 sm:px-3" data-testid="studio-workspace-toolbar">
    <button type="button" className={buttonClass(chaptersOpen)} aria-label={t('studio.layout.chapters')} aria-expanded={chaptersOpen} aria-controls="studio-chapters" onClick={onToggleChapters}>
      <PanelLeft size={16} /><span className="hidden sm:inline">{t('studio.layout.chapters')}</span>
    </button>
    <span className="mx-2 h-4 w-px shrink-0 bg-border/60" />
    <BookOpen size={14} className="hidden shrink-0 text-muted-foreground sm:block" />
    <div className="min-w-0 flex-1 px-1 text-xs">
      {draft === null ? (
        <button type="button" className="max-w-full truncate text-muted-foreground hover:text-foreground"
          title={t('library.rename')} onClick={() => { setRenameFailed(false); setDraft(title) }}>{title}</button>
      ) : (
        <div>
          <input autoFocus aria-label={t('library.rename')} maxLength={255} value={draft}
            className="w-full rounded border border-border bg-background px-1"
            onFocus={event => event.target.select()} onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Escape') setDraft(null)
              if (event.key === 'Enter') event.currentTarget.blur()
            }}
            onBlur={() => { void saveTitle() }} />
          {renameFailed && <span role="alert">{t('library.error.rename')}</span>}
        </div>
      )}
    </div>
    {canContinue && <button type="button" data-testid="studio-rail-continuation" className={buttonClass(writing)} aria-expanded={writing} onClick={onToggleWriting}>
      <PenLine size={15} /><span>{t('studio.rail.continuationTitle')}</span>
    </button>}
    <button type="button" className={buttonClass()} onClick={onOpenAtlas} onMouseEnter={onWarmAtlas} onFocus={onWarmAtlas} aria-label={t('studio.rail.atlasTitle')}>
      <Globe size={15} /><span className="hidden sm:inline">{t('studio.rail.atlasTitle')}</span>
    </button>
    <button type="button" className={buttonClass(assistantOpen)} aria-label={t('studio.assistant.toggleSidebar')} aria-expanded={assistantOpen} onClick={onToggleAssistant}>
      <PanelRight size={16} /><span className="hidden sm:inline">{t('studio.layout.assistant')}</span>
    </button>
  </header>
}
