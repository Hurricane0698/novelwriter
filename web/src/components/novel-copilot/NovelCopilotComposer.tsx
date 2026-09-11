import { useState, useRef, useEffect, useId, useContext } from 'react'
import { NovelCopilotContext } from './NovelCopilotContext'
import { ArrowUp } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function NovelCopilotComposer({ onSubmit, disabled = false, label, placeholder, sessionId }: {
  onSubmit: (text: string) => void
  disabled?: boolean
  label?: string
  placeholder?: string
  sessionId: string
}) {
  const { t } = useUiLocale()
  const copilot = useContext(NovelCopilotContext)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const inputId = useId()
  const value = copilot?.composerDrafts?.[sessionId] ?? drafts[sessionId] ?? ''
  const setValue = (next: string) => copilot?.setComposerDraft
    ? copilot.setComposerDraft(sessionId, next)
    : setDrafts(previous => ({ ...previous, [sessionId]: next }))
  const resolvedLabel = label ?? t('copilot.composer.defaultLabel')
  const submit = () => {
    if (disabled || !value.trim()) return
    onSubmit(value.trim())
    setValue('')
  }

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }, [value])

  return (
    <div className="rounded-lg border border-[var(--nw-copilot-border-strong)] bg-background/40 p-3 focus-within:border-accent/50">
      <label htmlFor={inputId} className="block text-xs text-muted-foreground">{resolvedLabel}</label>
      <textarea id={inputId} ref={textareaRef} value={value} onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return
          if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() }
        }}
        disabled={disabled} placeholder={placeholder ?? t('copilot.composer.defaultPlaceholder')}
        className="nw-scrollbar-thin mt-1 max-h-[160px] min-h-[72px] w-full resize-none bg-transparent py-2 text-sm leading-6 text-foreground placeholder:text-muted-foreground/65 focus:outline-none disabled:opacity-60" rows={2} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground/70">{t('copilot.composer.sendHint')}</span>
        <button type="button" onClick={submit} disabled={disabled || !value.trim()} aria-label={t('copilot.composer.send')}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-colors hover:bg-foreground/85 disabled:opacity-35">
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
