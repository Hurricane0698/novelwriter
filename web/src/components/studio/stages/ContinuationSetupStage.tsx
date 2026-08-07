// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { useQuery } from '@tanstack/react-query'
import { GlassCard } from '@/components/GlassCard'
import { AdvancedRow } from '@/components/workspace/AdvancedRow'
import { NwButton } from '@/components/ui/nw-button'
import { Textarea } from '@/components/ui/textarea'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { novelKeys } from '@/hooks/novel/keys'
import { api } from '@/services/api'


/**
 * Embeddable continuation-setup stage for the Studio center area.
 *
 * Pure presentation: all form state is owned by the parent via
 * `useContinuationSetupState`. This component mounts/unmounts freely
 * without losing user input.
 */
export function ContinuationSetupStage({
  novelId,
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
  contextChapterLimit,
  numVersions,
  onNumVersionsChange,
  temperature,
  onTemperatureChange,
  outlines,
  selectedOutlineIds,
  onSelectedOutlineIdsChange,
  outlineRange,
  onOutlineRangeChange,
  outlineGenerating,
  onCreateOutline,
  onGenerate,
  assistOpen,
  onToggleAssist,
}: {
  novelId: number
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
  contextChapterLimit: number
  numVersions: string
  onNumVersionsChange: (next: string) => void
  temperature: string
  onTemperatureChange: (next: string) => void
  outlines: Array<{ id: number; start_chapter: number; end_chapter: number; title: string; content: string }>
  selectedOutlineIds: number[]
  onSelectedOutlineIdsChange: (next: number[]) => void
  outlineRange: string
  onOutlineRangeChange: (next: string) => void
  outlineGenerating: boolean
  onCreateOutline: () => void
  onGenerate: () => void
  assistOpen?: boolean
  onToggleAssist?: () => void
}) {
  const { t } = useUiLocale()
  const { data: chapter, isLoading: chapterLoading } = useQuery({
    queryKey: novelKeys.chapter(novelId, chapterNum),
    queryFn: () => api.getChapter(novelId, chapterNum),
  })

  const wordCount = chapter?.content?.length ?? 0
  const parsedContextChapters = Number.parseInt(contextChapters, 10)
  const effectiveContextChapters = Number.isFinite(parsedContextChapters)
    ? Math.max(1, Math.min(contextChapterLimit, parsedContextChapters))
    : 1
  const parsedTargetChars = Number.parseInt(selectedLength, 10)
  const effectiveTargetChars = Number.isFinite(parsedTargetChars)
    ? Math.max(1000, Math.min(20000, parsedTargetChars))
    : 3000
  // Conservative estimate for Chinese prose: ~5k chars/chapter and ~2 chars/token.
  const estimatedSourceTokens = Math.ceil(effectiveContextChapters * 5000 / 2)
  const estimatedOutputTokens = Math.ceil(effectiveTargetChars * 1.1 / 2)
  const estimatedTotalTokens = estimatedSourceTokens + estimatedOutputTokens + 5000

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
          <PlainTextContent
            isLoading={chapterLoading}
            content={chapter?.content}
            loadingLabel={t('continuation.setup.loadingChapter')}
            emptyLabel={t('continuation.setup.emptyChapter')}
          />
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

        {/* Custom length */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('continuation.setup.length')}
          </label>
          <AdvancedRow label="目标字数" desc="1000–20000" value={selectedLength} onChange={onSelectedLengthChange} type="number" min={1000} max={20000} step={100} />
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
              <AdvancedRow label={t('continuation.setup.contextChapters')} desc={`1–${contextChapterLimit}（全书）`} value={contextChapters} onChange={onContextChaptersChange} type="number" min={1} max={contextChapterLimit} step={1} />
              <p className="-mt-2 text-[11px] leading-relaxed text-muted-foreground">
                预计上下文约 {Math.round(estimatedSourceTokens / 100) / 10}k tokens；含本次输出约 {Math.round(estimatedTotalTokens / 100) / 10}k tokens。
              </p>
              <div className="border-t border-border/50 pt-3">
                <div className="mb-2 text-xs font-medium text-foreground">剧情大纲</div>
                <div className="flex gap-2">
                  <input className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs" placeholder="例如 1-100" value={outlineRange} onChange={(e) => onOutlineRangeChange(e.target.value)} />
                  <NwButton type="button" variant="accentOutline" className="h-8 px-3 text-xs" onClick={onCreateOutline} disabled={outlineGenerating}>{outlineGenerating ? '生成中…' : '生成大纲'}</NwButton>
                </div>
                <div className="mt-2 max-h-40 space-y-1 overflow-auto">
                  {outlines.length === 0 ? <div className="text-[11px] text-muted-foreground">还没有生成的大纲</div> : outlines.map((outline) => (
                    <label key={outline.id} className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1 text-xs hover:bg-muted/40">
                      <input type="checkbox" className="mt-0.5" checked={selectedOutlineIds.includes(outline.id)} onChange={(e) => onSelectedOutlineIdsChange(e.target.checked ? [...selectedOutlineIds, outline.id] : selectedOutlineIds.filter((id) => id !== outline.id))} />
                      <span className="min-w-0 truncate">{outline.title || `第${outline.start_chapter}—${outline.end_chapter}章`}</span>
                    </label>
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
    </div>
  )
}
