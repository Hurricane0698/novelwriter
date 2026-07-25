import type { ComponentType } from 'react'
import { Bot, BookOpen, Check, FileText, Sparkles } from 'lucide-react'
import type { DemoFirstOnboardingStatus } from '@/lib/demoFirstOnboardingStorage'
import { cn } from '@/lib/utils'
import { GlassSurface } from '@/components/ui/glass-surface'
import { NwButton } from '@/components/ui/nw-button'
import { useUiLocale } from '@/contexts/UiLocaleContext'

interface DemoGuideStepCardProps {
  title: string
  description: string
  actionLabel: string
  complete: boolean
  onClick: () => void
  onWarm?: () => void
  icon: ComponentType<{ className?: string }>
  meta?: string
  completeLabel: string
}

function DemoGuideStepCard({
  title,
  description,
  actionLabel,
  complete,
  onClick,
  onWarm,
  icon: Icon,
  meta,
  completeLabel,
}: DemoGuideStepCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={onWarm}
      onFocus={onWarm}
      className={cn(
        'group w-full rounded-[20px] border px-3.5 py-2.5 text-left transition-all',
        complete
          ? 'border-[hsl(var(--color-success)/0.28)] bg-[linear-gradient(155deg,hsl(var(--color-success)/0.12),transparent_78%)]'
          : 'border-[var(--nw-glass-border)] bg-[linear-gradient(155deg,hsl(var(--background)/0.16),transparent_78%)] hover:border-[hsl(var(--accent)/0.24)] hover:bg-[linear-gradient(155deg,hsl(var(--accent)/0.11),transparent_78%)]',
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-[14px] border shadow-[0_8px_18px_rgba(15,23,42,0.10)]',
            complete
              ? 'border-[hsl(var(--color-success)/0.26)] bg-[hsl(var(--color-success)/0.14)] text-[hsl(var(--color-success))]'
              : 'border-[hsl(var(--accent)/0.24)] bg-[hsl(var(--accent)/0.12)] text-[hsl(var(--accent))]',
          )}
        >
          {complete ? <Check className="h-4 w-4" /> : <Icon className="h-4.5 w-4.5" />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-foreground">{title}</div>
            {complete ? (
              <span className="inline-flex items-center rounded-full border border-[hsl(var(--color-success)/0.24)] bg-[hsl(var(--color-success)/0.10)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[hsl(var(--color-success))]">
                {completeLabel}
              </span>
            ) : null}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-muted-foreground/84">{description}</div>
          {meta ? (
            <div className="mt-1.5 text-[11px] leading-5 text-muted-foreground/76">{meta}</div>
          ) : null}
          <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[hsl(var(--accent))]">
            {actionLabel}
          </div>
        </div>
      </div>
    </button>
  )
}

export function DemoFirstWritingOnboarding({
  className,
  status,
  progressCount,
  totalSteps,
  chapterVisited,
  atlasVisited,
  writeVisited,
  copilotVisited,
  chapterCount,
  worldEntityCount,
  worldSystemCount,
  latestChapterReference,
  windowIndexStatusText,
  onOpenChapter,
  onOpenAtlas,
  onWarmAtlas,
  onOpenWrite,
  onOpenCopilot,
  onSkip,
}: {
  className?: string
  status: DemoFirstOnboardingStatus
  progressCount: number
  totalSteps: number
  chapterVisited: boolean
  atlasVisited: boolean
  writeVisited: boolean
  copilotVisited: boolean
  chapterCount: number
  worldEntityCount: number
  worldSystemCount: number
  latestChapterReference: string | null
  windowIndexStatusText: string
  onOpenChapter: () => void
  onOpenAtlas: () => void
  onWarmAtlas?: () => void
  onOpenWrite: () => void
  onOpenCopilot: () => void
  onSkip: () => void
}) {
  const { t } = useUiLocale()
  const progressRatio = totalSteps <= 0 ? 0 : Math.min(progressCount / totalSteps, 1)
  const hasBreakpoint = latestChapterReference !== null

  const title = status === 'completed'
    ? t('studio.demoGuide.completedTitle')
    : status === 'skipped'
      ? t('studio.demoGuide.skippedTitle')
      : t('studio.demoGuide.title')
  const description = status === 'completed'
    ? t('studio.demoGuide.completedDescription')
    : status === 'skipped'
      ? t('studio.demoGuide.skippedDescription')
      : t('studio.demoGuide.description')

  return (
    <GlassSurface
      variant="container"
      className={cn(
        'nw-preserve-backdrop-blur flex min-h-0 flex-col overflow-hidden rounded-[24px] border border-[var(--nw-glass-border)] p-3.5 sm:p-4',
        className,
      )}
      data-testid="demo-first-onboarding"
    >
      <div className="nw-scrollbar-thin flex min-h-0 flex-col gap-3 overflow-y-auto pr-1 sm:gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-muted-foreground/72">
                {t('studio.demoGuide.eyebrow')}
              </div>
              <span className="inline-flex items-center rounded-full border border-[hsl(var(--accent)/0.22)] bg-[hsl(var(--accent)/0.10)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[hsl(var(--accent))]">
                {t('studio.demoGuide.progress', { current: progressCount, total: totalSteps })}
              </span>
            </div>
            <div className="mt-2 text-[16px] font-semibold leading-6 text-foreground">{title}</div>
            <div className="mt-1 text-[12px] leading-5 text-muted-foreground/84">{description}</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-background/30">
            <div
              className="h-full rounded-full bg-[linear-gradient(90deg,hsl(var(--accent)),hsl(var(--accent)/0.52))] transition-[width] duration-300 ease-out"
              style={{ width: `${progressRatio * 100}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/15 px-2.5 py-1 text-[11px] text-foreground/88">
              {t('studio.demoGuide.summaryChapters', { count: chapterCount })}
            </span>
            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/15 px-2.5 py-1 text-[11px] text-foreground/88">
              {t('studio.demoGuide.summaryWorld', {
                entityCount: worldEntityCount,
                systemCount: worldSystemCount,
              })}
            </span>
            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/15 px-2.5 py-1 text-[11px] text-foreground/88">
              {latestChapterReference
                ? t('studio.demoGuide.summaryLatest', { chapter: latestChapterReference })
                : t('studio.demoGuide.summaryLatestFallback')}
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <DemoGuideStepCard
            icon={FileText}
            title={t('studio.demoGuide.chapterTitle')}
            description={t('studio.demoGuide.chapterDescription')}
            actionLabel={t('studio.demoGuide.chapterAction')}
            complete={chapterVisited}
            onClick={onOpenChapter}
            completeLabel={t('studio.demoGuide.complete')}
          />
          <DemoGuideStepCard
            icon={Sparkles}
            title={t('studio.demoGuide.worldModelTitle')}
            description={t('studio.demoGuide.worldModelDescription')}
            actionLabel={t('studio.demoGuide.worldModelAction')}
            complete={atlasVisited}
            onClick={onOpenAtlas}
            onWarm={onWarmAtlas}
            completeLabel={t('studio.demoGuide.complete')}
          />
          <DemoGuideStepCard
            icon={BookOpen}
            title={t('studio.demoGuide.breakpointTitle')}
            description={hasBreakpoint
              ? t('studio.demoGuide.breakpointDescription', { chapter: latestChapterReference })
              : t('studio.demoGuide.breakpointDescriptionFallback')}
            actionLabel={t('studio.demoGuide.breakpointAction')}
            complete={writeVisited}
            onClick={onOpenWrite}
            completeLabel={t('studio.demoGuide.complete')}
          />
          <DemoGuideStepCard
            icon={Bot}
            title={t('studio.demoGuide.copilotTitle')}
            description={t('studio.demoGuide.copilotDescription')}
            actionLabel={t('studio.demoGuide.copilotAction')}
            complete={copilotVisited}
            onClick={onOpenCopilot}
            meta={`${t('studio.demoGuide.windowIndexLabel')} ${windowIndexStatusText}`}
            completeLabel={t('studio.demoGuide.complete')}
          />
        </div>

        {status !== 'completed' ? (
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] leading-5 text-muted-foreground/76">
              {t('studio.demoGuide.autoHideHint')}
            </div>
            <NwButton
              variant="ghost"
              className="rounded-full px-3 py-1.5 text-sm"
              onClick={onSkip}
              data-testid="demo-first-onboarding-skip"
            >
              {t('studio.demoGuide.skip')}
            </NwButton>
          </div>
        ) : null}
      </div>
    </GlassSurface>
  )
}
