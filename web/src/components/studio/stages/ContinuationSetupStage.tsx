// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { ChevronDown, ChevronUp, Sparkles, Trash2 } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { useQuery } from '@tanstack/react-query'
import { GlassCard } from '@/components/GlassCard'
import { AdvancedRow } from '@/components/workspace/AdvancedRow'
import { NwButton } from '@/components/ui/nw-button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Textarea } from '@/components/ui/textarea'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import { MarkdownContent } from '@/components/ui/markdown-content'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { novelKeys } from '@/hooks/novel/keys'
import { api } from '@/services/api'
import { LENGTH_OPTIONS } from '@/hooks/novel/useContinuationSetupState'
import { isMarkdownContentFormat } from '@/lib/novelContentFormat'
import type { NovelContentFormat, NovelOutline } from '@/types/api'

/**
 * Embeddable continuation-setup stage for the Studio center area.
 *
 * Pure presentation: all form state is owned by the parent via
 * `useContinuationSetupState`. This component mounts/unmounts freely
 * without losing user input.
 */
export function ContinuationSetupStage({
  novelId,
  contentFormat,
  chapterNum,
  chapterReference,
  instruction,
  onInstructionChange,
  selectedLength,
  onSelectedLengthChange,
  advancedOpen,
  onAdvancedOpenChange,
  contextChapters,
  onContextChaptersChange,
  numVersions,
  onNumVersionsChange,
  temperature,
  onTemperatureChange,
  outlines,
  outlinesLoading,
  outlineError,
  selectedOutlineIds,
  onSelectedOutlineIdsChange,
  outlineRange,
  onOutlineRangeChange,
  outlineGenerating,
  outlineDeletingId,
  onCreateOutline,
  onDeleteOutline,
  onGenerate,
  assistOpen,
  onToggleAssist,
}: {
  novelId: number
  contentFormat: NovelContentFormat
  chapterNum: number
  chapterReference: string | null
  instruction: string
  onInstructionChange: (next: string) => void
  selectedLength: string
  onSelectedLengthChange: (next: string) => void
  advancedOpen: boolean
  onAdvancedOpenChange: (next: boolean) => void
  contextChapters: string
  onContextChaptersChange: (next: string) => void
  numVersions: string
  onNumVersionsChange: (next: string) => void
  temperature: string
  onTemperatureChange: (next: string) => void
  outlines: NovelOutline[]
  outlinesLoading: boolean
  outlineError: string | null
  selectedOutlineIds: number[]
  onSelectedOutlineIdsChange: (next: number[]) => void
  outlineRange: string
  onOutlineRangeChange: (next: string) => void
  outlineGenerating: boolean
  outlineDeletingId: number | null
  onCreateOutline: () => void
  onDeleteOutline: (outlineId: number) => Promise<void>
  onGenerate: () => void
  assistOpen?: boolean
  onToggleAssist?: () => void
}) {
  const { t } = useUiLocale()
  const { confirm, dialogProps } = useConfirmDialog()
  const isMarkdown = isMarkdownContentFormat(contentFormat)
  const { data: chapter, isLoading: chapterLoading } = useQuery({
    queryKey: novelKeys.chapter(novelId, chapterNum),
    queryFn: () => api.getChapter(novelId, chapterNum),
  })

  const wordCount = chapter?.content?.length ?? 0
  const handleDeleteOutline = async (outline: NovelOutline) => {
    const confirmed = await confirm({
      title: t('continuation.setup.outline.delete'),
      description: t('continuation.setup.outline.deleteConfirm', { title: outline.title }),
      confirmText: t('continuation.setup.outline.delete'),
      tone: 'destructive',
    })
    if (confirmed) await onDeleteOutline(outline.id)
  }

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Chapter Preview */}
      <div className="flex-1 min-w-0 flex flex-col gap-6 px-8 py-8 lg:px-12 overflow-hidden">
        <div className="flex items-center justify-between shrink-0">
          <GlassCard variant="control" className="rounded-xl px-4 py-2">
            <span className="text-sm font-medium text-foreground">
              {t('continuation.setup.basedOn', { chapter: chapterReference ?? `Ch. ${chapterNum}` })}
            </span>
          </GlassCard>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t('continuation.setup.charCount', { count: wordCount })}
            </span>
            {onToggleAssist ? <AssistToggleButton active={assistOpen} onClick={onToggleAssist} /> : null}
          </div>
        </div>

        <GlassCard className="flex-1 overflow-auto rounded-xl p-6 sm:p-8 nw-scrollbar-thin">
          {isMarkdown ? (
            <MarkdownContent
              isLoading={chapterLoading}
              content={chapter?.content}
              loadingLabel={t('continuation.setup.loadingChapter')}
              emptyLabel={t('continuation.setup.emptyChapter')}
            />
          ) : (
            <PlainTextContent
              isLoading={chapterLoading}
              content={chapter?.content}
              loadingLabel={t('continuation.setup.loadingChapter')}
              emptyLabel={t('continuation.setup.emptyChapter')}
            />
          )}
        </GlassCard>
      </div>

      {/* Parameter Panel */}
      <aside className="w-[420px] shrink-0 border-l border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-6 flex flex-col gap-6 overflow-auto nw-scrollbar-thin">
        <h2 className="font-mono text-base font-semibold text-foreground">
          {t('continuation.setup.title')}
        </h2>

        {/* Instruction */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('continuation.setup.instruction')}
          </label>
          <Textarea
            value={instruction}
            onChange={e => onInstructionChange(e.target.value)}
            placeholder={t('continuation.setup.instructionPlaceholder')}
            className="min-h-[80px] resize-none text-[13px] leading-relaxed bg-[var(--nw-glass-bg)] border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
          />
        </div>

        {/* Length */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('continuation.setup.length')}
          </label>
          <div className="flex gap-2">
            {LENGTH_OPTIONS.map(option => {
              const isDisabled = option.disabled
              const isSelected = !isDisabled && selectedLength === option.value
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => !isDisabled && onSelectedLengthChange(option.value)}
                  disabled={isDisabled}
                  className={cn(
                    'flex-1 h-9 rounded-[10px] border text-sm font-mono transition-colors',
                    isDisabled
                      ? 'bg-muted/50 border-muted text-muted-foreground/40 cursor-not-allowed'
                      : isSelected
                      ? 'bg-[hsl(var(--accent)/0.12)] border-accent text-accent font-semibold'
                      : 'bg-[var(--nw-glass-bg)] border-[var(--nw-glass-border)] text-muted-foreground hover:bg-[var(--nw-glass-bg-hover)]'
                  )}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Advanced Toggle */}
        <button
          type="button"
          onClick={() => onAdvancedOpenChange(!advancedOpen)}
          className="w-full flex items-center justify-between py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <span>{t('continuation.setup.advancedSettings')}</span>
          {advancedOpen ? (
            <ChevronUp size={14} className="text-muted-foreground" />
          ) : (
            <ChevronDown size={14} className="text-muted-foreground" />
          )}
        </button>

        {/* Advanced Panel */}
        <div
          className={cn(
            'grid transition-[grid-template-rows] duration-200',
            advancedOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          )}
        >
          <div className="overflow-hidden">
            <GlassCard className="rounded-xl p-4 flex flex-col gap-4">
              <AdvancedRow label={t('continuation.setup.contextChapters')} desc="1–5" value={contextChapters} onChange={onContextChaptersChange} type="number" min={1} max={5} step={1} />
              <div className="border-t border-border/50 pt-3">
                <div className="mb-1 text-xs font-medium text-foreground">
                  {t('continuation.setup.outline.title')}
                </div>
                <p className="mb-2 text-[11px] leading-relaxed text-muted-foreground">
                  {t('continuation.setup.outline.description')}
                </p>
                <div className="flex gap-2">
                  <input
                    className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
                    aria-label={t('continuation.setup.outline.rangeLabel')}
                    placeholder={t('continuation.setup.outline.rangePlaceholder')}
                    value={outlineRange}
                    onChange={event => onOutlineRangeChange(event.target.value)}
                  />
                  <NwButton
                    variant="accentOutline"
                    className="h-8 px-3 text-xs"
                    onClick={onCreateOutline}
                    disabled={outlineGenerating || outlineRange.trim().length === 0}
                  >
                    {outlineGenerating
                      ? t('continuation.setup.outline.generating')
                      : t('continuation.setup.outline.create')}
                  </NwButton>
                </div>
                {outlineError ? (
                  <p className="mt-2 text-[11px] leading-relaxed text-[hsl(var(--color-danger))]" role="alert">
                    {outlineError}
                  </p>
                ) : null}
                <div className="mt-2 max-h-40 space-y-1 overflow-auto">
                  {outlinesLoading ? (
                    <div className="text-[11px] text-muted-foreground">
                      {t('continuation.setup.outline.loading')}
                    </div>
                  ) : outlines.length === 0 ? (
                    <div className="text-[11px] text-muted-foreground">
                      {t('continuation.setup.outline.empty')}
                    </div>
                  ) : outlines.map(outline => (
                    <div key={outline.id} className="flex items-start gap-1 rounded-md px-1 py-1 text-xs hover:bg-muted/40">
                      <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2">
                        <input
                          type="checkbox"
                          className="mt-0.5"
                          checked={selectedOutlineIds.includes(outline.id)}
                          onChange={event => onSelectedOutlineIdsChange(
                            event.target.checked
                              ? [...selectedOutlineIds, outline.id]
                              : selectedOutlineIds.filter(id => id !== outline.id)
                          )}
                        />
                        <span className="min-w-0 truncate" title={outline.title}>
                          {outline.title}
                        </span>
                      </label>
                      <NwButton
                        variant="ghost"
                        className="h-6 w-6 shrink-0 p-0 text-[hsl(var(--color-danger))]"
                        aria-label={t('continuation.setup.outline.deleteNamed', { title: outline.title })}
                        disabled={outlineDeletingId === outline.id}
                        onClick={() => void handleDeleteOutline(outline)}
                      >
                        <Trash2 size={12} />
                      </NwButton>
                    </div>
                  ))}
                </div>
              </div>
              <AdvancedRow label={t('continuation.setup.numVersions')} desc="1–2" value={numVersions} onChange={onNumVersionsChange} type="number" min={1} max={2} step={1} />
              <AdvancedRow label={t('continuation.setup.temperature')} desc="0.0–2.0" value={temperature} onChange={onTemperatureChange} type="number" min={0} max={2} step={0.1} />
            </GlassCard>
          </div>
        </div>

        <div className="flex-1" />

        {/* Generate Button */}
        <NwButton
          data-testid="studio-generate-button"
          onClick={onGenerate}
          disabled={!novelId}
          variant="accent"
          className="w-full h-12 rounded-xl shadow-[0_4px_24px_hsl(var(--accent)/0.25)] text-[15px] font-semibold disabled:cursor-default"
        >
          <Sparkles size={18} />
          {t('continuation.setup.generate')}
        </NwButton>
      </aside>
      <ConfirmDialog {...dialogProps} />
    </div>
  )
}
