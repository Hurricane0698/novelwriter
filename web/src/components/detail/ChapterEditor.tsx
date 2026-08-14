import { useRef, useState } from 'react'
import { Check, Redo2, Undo2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NwButton } from '@/components/ui/nw-button'
import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { MarkdownContent } from '@/components/ui/markdown-content'
import type { TextAnnotation } from '@/components/ui/annotated-text'
import {
  MARKDOWN_CHAPTER_BODY_INVALID,
  type ChapterMutationErrorCode,
} from '@/lib/chapterMutationError'
import { isMarkdownContentFormat } from '@/lib/novelContentFormat'
import type { NovelContentFormat } from '@/types/api'

export type AutoSaveStatus = 'saved' | 'unsaved' | 'idle'
export type ChapterEditorSaveErrorCode = ChapterMutationErrorCode | 'chapter_save_failed'

/**
 * Scroll a textarea so that the character at `charIndex` is visible.
 * Uses a mirror div to measure the pixel offset of the target line,
 * accounting for word-wrap and CJK text.
 */
function scrollTextareaTo(ta: HTMLTextAreaElement, charIndex: number) {
  const mirror = document.createElement('div')
  const cs = getComputedStyle(ta)
  Object.assign(mirror.style, {
    position: 'absolute',
    top: '-9999px',
    left: '-9999px',
    width: cs.width,
    padding: cs.padding,
    fontSize: cs.fontSize,
    fontFamily: cs.fontFamily,
    lineHeight: cs.lineHeight,
    letterSpacing: cs.letterSpacing,
    whiteSpace: 'pre-wrap',
    wordWrap: 'break-word',
    overflow: 'hidden',
  })
  mirror.textContent = ta.value.substring(0, charIndex)
  document.body.appendChild(mirror)
  const targetY = mirror.scrollHeight
  document.body.removeChild(mirror)
  // Place the target roughly 1/3 from the top of the visible area
  ta.scrollTop = Math.max(0, targetY - ta.clientHeight / 3)
}

export function ChapterEditor({
  textareaRef,
  value,
  onChange,
  onSelectionChange,
  cursorInfo,
  autoSaveStatus,
  saveErrorCode,
  onUndo,
  onRedo,
  onCancel,
  onSave,
  warningTerms,
  previewAnnotations,
  contentFormat,
}: {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  value: string
  onChange: (next: string) => void
  onSelectionChange: () => void
  cursorInfo: { para: number; col: number }
  autoSaveStatus: AutoSaveStatus
  saveErrorCode: ChapterEditorSaveErrorCode | null
  onUndo: () => void
  onRedo: () => void
  onCancel: () => void
  onSave: () => void
  warningTerms?: { code: string; term: string }[]
  previewAnnotations?: TextAnnotation[]
  contentFormat: NovelContentFormat
}) {
  const { t } = useUiLocale()
  const wordCount = value.replace(/\s/g, '').length
  const [markdownTab, setMarkdownTab] = useState<'source' | 'preview'>('source')
  const isMarkdown = isMarkdownContentFormat(contentFormat)
  const saveErrorMessage = saveErrorCode === null
    ? null
    : saveErrorCode === MARKDOWN_CHAPTER_BODY_INVALID
      ? t('editor.error.markdownChapterBodyInvalid')
      : t('editor.error.saveFailed')

  // Track last-found offset per term so repeated clicks cycle through occurrences
  const lastPosRef = useRef<Map<string, number>>(new Map())

  const jumpTextareaToTerm = (term: string) => {
    const ta = textareaRef.current
    if (!ta) return
    const lastPos = lastPosRef.current.get(term) ?? -1
    let idx = ta.value.indexOf(term, lastPos + 1)
    if (idx === -1) {
      // Wrap around to the beginning
      idx = ta.value.indexOf(term)
    }
    if (idx === -1) return
    lastPosRef.current.set(term, idx)
    ta.focus()
    ta.setSelectionRange(idx, idx + term.length)
    scrollTextareaTo(ta, idx)
  }

  const handleJumpToTerm = (term: string) => {
    if (isMarkdown && markdownTab === 'preview') {
      setMarkdownTab('source')
      requestAnimationFrame(() => jumpTextareaToTerm(term))
      return
    }
    jumpTextareaToTerm(term)
  }

  return (
    <GlassCard className="flex-1 flex flex-col overflow-hidden rounded-xl">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--nw-glass-border)]">
        <NwButton
          onClick={onUndo}
          variant="ghost"
          className="w-8 h-8 rounded-md"
          title={t('editor.undo')}
        >
          <Undo2 size={16} />
        </NwButton>
        <NwButton
          onClick={onRedo}
          variant="ghost"
          className="w-8 h-8 rounded-md"
          title={t('editor.redo')}
        >
          <Redo2 size={16} />
        </NwButton>
        {isMarkdown ? (
          <div className="ml-2 flex items-center rounded-lg border border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.03)] p-0.5">
            {(['source', 'preview'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setMarkdownTab(tab)}
                className={cn(
                  'rounded-md px-3 py-1 text-xs font-medium transition-colors',
                  markdownTab === tab
                    ? 'bg-[hsl(var(--accent)/0.15)] text-accent'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {tab === 'source' ? t('editor.markdown.source') : t('editor.markdown.preview')}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {warningTerms && warningTerms.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--nw-glass-border)]">
          <span className="text-xs text-muted-foreground shrink-0">{t('editor.driftWarning')}</span>
          <div className="flex flex-wrap gap-1.5">
            {warningTerms.map(w => (
              <button
                key={`${w.code}-${w.term}`}
                type="button"
                onClick={() => handleJumpToTerm(w.term)}
                className="text-xs font-medium px-2 py-0.5 rounded-md bg-[hsl(217,91%,60%,0.15)] text-[hsl(217,91%,80%)] hover:bg-[hsl(217,91%,60%,0.25)] transition-colors cursor-pointer"
              >
                {w.term}
              </button>
            ))}
          </div>
        </div>
      )}

      {isMarkdown && markdownTab === 'preview' ? (
        <div className="min-h-0 flex-1 overflow-auto px-8 py-6 nw-scrollbar-thin" data-testid="markdown-editor-preview">
          <MarkdownContent content={value} maxWidth annotations={previewAnnotations} />
        </div>
      ) : (
        <textarea
          data-testid="chapter-editor-textarea"
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onSelect={onSelectionChange}
          onClick={onSelectionChange}
          onKeyUp={onSelectionChange}
          className="flex-1 resize-none bg-transparent px-8 py-6 outline-none text-[15px] leading-[2] text-foreground caret-accent nw-scrollbar-thin"
        />
      )}

      {saveErrorMessage ? (
        <div
          role="alert"
          data-testid="chapter-editor-save-error"
          className="shrink-0 border-t border-[hsl(var(--color-danger)/0.25)] bg-[hsl(var(--color-danger)/0.08)] px-4 py-2 text-sm text-[hsl(var(--color-danger))]"
        >
          {saveErrorMessage}
        </div>
      ) : null}

      <div className="flex items-center justify-between px-4 py-2 border-t border-[var(--nw-glass-border)]">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{t('editor.charCount', { count: wordCount.toLocaleString() })}</span>
          <span>{t('editor.cursorPosition', { para: cursorInfo.para, col: cursorInfo.col })}</span>
          <span className="inline-flex items-center gap-1.5">
            {autoSaveStatus !== 'idle' ? (
              <>
                <span
                  className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    autoSaveStatus === 'saved'
                      ? 'bg-[hsl(var(--color-status-confirmed))]'
                      : 'bg-muted-foreground'
                  )}
                />
                <span>
                  {autoSaveStatus === 'saved' ? t('editor.autoSaved') : t('editor.unsaved')}
                </span>
              </>
            ) : null}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <NwButton
            onClick={onCancel}
            variant="glass"
            className="rounded-lg px-3 py-1.5 text-sm"
          >
            {t('dialog.cancel')}
          </NwButton>
          <NwButton
            onClick={onSave}
            variant="accent"
            className="rounded-lg px-3 py-1.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
          >
            <Check size={14} />
            {t('editor.save')}
          </NwButton>
        </div>
      </div>
    </GlassCard>
  )
}
