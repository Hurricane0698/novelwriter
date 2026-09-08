import type { Dispatch, SetStateAction } from 'react'
import { MoreHorizontal, Pencil, Trash2, Upload } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { GlassSurface } from '@/components/ui/glass-surface'
import { NwButton } from '@/components/ui/nw-button'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { formatRelativeTime } from '@/lib/formatRelativeTime'
import { formatChapterBadgeLabel, getChapterDisplayTitle, type ChapterIdentityLike } from '@/lib/chaptersPlainText'
import type { ChapterMeta } from '@/types/api'

type BooleanSetter = Dispatch<SetStateAction<boolean>>

interface StudioChapterToolbarProps {
  currentMeta: ChapterMeta | undefined
  currentChapterIdentity: ChapterIdentityLike | null
  content: string
  canEdit: boolean
  canDelete: boolean
  editor: {
    editMode: boolean
    editingTitle: boolean
    titleDraft: string
    setTitleDraft: (value: string) => void
    setEditingTitle: BooleanSetter
    handleTitleSave: () => void
    toggleEdit: () => void
  }
  actions: {
    isOpen: boolean
    onOpenChange: BooleanSetter
    exportChapter: () => void
    exportAll: () => Promise<void>
    deleteChapter: () => Promise<void>
  }
  assistOpen: boolean
  onToggleAssist: () => void
}

/** Chapter metadata and commands; save ownership stays in the mounted Studio editor. */
export function StudioChapterToolbar({
  currentMeta, currentChapterIdentity, content, canEdit, canDelete,
  editor, actions, assistOpen: showAssistRail, onToggleAssist: handleToggleAssist,
}: StudioChapterToolbarProps) {
  const { t } = useUiLocale()
  const { editMode, editingTitle, titleDraft, setTitleDraft, setEditingTitle, handleTitleSave, toggleEdit } = editor
  const {
    isOpen: showMoreActions, onOpenChange: setShowMoreActions,
    exportChapter: handleExportChapter, exportAll: handleExportAll, deleteChapter: handleDeleteChapter,
  } = actions
  const displayTitle = currentChapterIdentity ? getChapterDisplayTitle(currentChapterIdentity.title) : ''
  const wordCount = content.replace(/\s/g, '').length

  return (
    <div className="shrink-0 border-b border-[var(--nw-glass-border)] pb-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1 space-y-3">
          {currentMeta ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] font-medium text-foreground/88">
                  {formatChapterBadgeLabel(currentChapterIdentity ?? currentMeta)}
                </span>
                <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                  {editMode ? t('studio.chapter.editing') : t('studio.chapter.reading')}
                </span>
              </div>

              <div className="min-w-0">
                {editingTitle ? (
                  <input
                    autoFocus
                    value={titleDraft}
                    onChange={e => setTitleDraft(e.target.value)}
                    onBlur={() => { handleTitleSave() }}
                    onKeyDown={e => { if (e.key === 'Enter') handleTitleSave(); if (e.key === 'Escape') setEditingTitle(false) }}
                    className="w-full max-w-[720px] font-mono text-[22px] font-semibold text-foreground bg-[var(--nw-glass-bg)] border border-[hsl(var(--accent)/0.35)] rounded-md px-2 py-1 outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0"
                    placeholder={t('studio.chapter.titlePlaceholder')}
                  />
                ) : (
                  <div
                    onDoubleClick={() => { setTitleDraft(displayTitle); setEditingTitle(true) }}
                    title={t('studio.chapter.titleEditHint')}
                    className="cursor-text"
                  >
                    {displayTitle ? (
                      <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground break-words">
                        {displayTitle}
                      </h1>
                    ) : (
                      <span className="text-[22px] text-muted-foreground italic">{t('studio.chapter.titleAddHint')}</span>
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span>{t('studio.chapter.charCount', { count: wordCount.toLocaleString() })}</span>
                {currentMeta.created_at ? (
                  <span>{t('studio.chapter.updated', { time: formatRelativeTime(currentMeta.created_at) })}</span>
                ) : null}
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                {t('studio.header.workspace')}
              </span>
              <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground">
                {t('studio.header.selectChapter')}
              </h1>
            </div>
          )}
        </div>

        <div className="flex w-full flex-col gap-2.5 xl:w-auto xl:max-w-[520px] xl:items-end">
          <div className="flex flex-wrap gap-2">
            <NwButton
              onClick={toggleEdit}
              disabled={!canEdit}
              variant="accentOutline"
              className="rounded-[10px] px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
            >
              <Pencil size={14} />
              {t('studio.chapter.edit')}
            </NwButton>

            <div className="relative">
              <NwButton
                onClick={() => setShowMoreActions((prev) => !prev)}
                variant="glass"
                className="h-10 w-10 rounded-[10px] p-0 text-sm font-medium"
                aria-haspopup="menu"
                aria-expanded={showMoreActions}
                aria-label={t('studio.actions.moreActions')}
                title={t('studio.actions.moreActions')}
              >
                <MoreHorizontal size={14} />
              </NwButton>

              {showMoreActions ? (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowMoreActions(false)}
                  />
                  <GlassSurface
                    variant="floating"
                    className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[188px] rounded-[16px] p-1.5"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setShowMoreActions(false)
                        handleExportChapter()
                      }}
                      className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
                    >
                      <Upload size={14} className="text-muted-foreground" />
                      <span>{t('studio.actions.exportChapter')}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowMoreActions(false)
                        handleExportAll()
                      }}
                      className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
                    >
                      <Upload size={14} className="text-muted-foreground" />
                      <span>{t('studio.actions.exportAllChapters')}</span>
                    </button>

                    {canDelete ? (
                      <>
                        <div className="mx-2 my-1 h-px bg-[var(--nw-glass-border)]" />
                        <button
                          type="button"
                          onClick={() => {
                            setShowMoreActions(false)
                            void handleDeleteChapter()
                          }}
                          className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-[hsl(var(--color-danger))] transition-colors hover:bg-[hsl(var(--color-danger)/0.10)]"
                        >
                          <Trash2 size={14} />
                          <span>{t('studio.chapter.delete')}</span>
                        </button>
                      </>
                    ) : null}
                  </GlassSurface>
                </>
              ) : null}
            </div>

            <AssistToggleButton active={showAssistRail} onClick={handleToggleAssist} />
          </div>
        </div>
      </div>
    </div>
  )
}
