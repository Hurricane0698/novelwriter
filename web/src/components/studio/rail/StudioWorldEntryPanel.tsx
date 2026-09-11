import '@/lib/uiMessagePacks/copilot'
import { useState } from 'react'
import { Globe, Sparkles } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { WorldEntryLifecycleCard } from '@/components/world-model/shared/WorldEntryLifecycleCard'
import { resolveWorldEntryReviewKind } from '@/lib/worldEntryLifecycle'
import { useWorldEntryLifecycle } from '@/hooks/world/useWorldEntryLifecycle'
import type {
  WorldEntryHandoffState,
  WorldEntryPendingState,
} from '@/components/novel-shell/NovelShellRouteState'

export function StudioWorldEntryPanel({
  novelId,
  worldEntityCount,
  worldSystemCount,
  handoff,
  pending,
  onHandoffChange,
  onPendingHandoffChange,
  onOpenAtlas,
  onOpenAtlasReview,
  onWarmAtlas,
  prominence = 'compact',
}: {
  novelId: number
  worldEntityCount: number
  worldSystemCount: number
  handoff: WorldEntryHandoffState | null
  pending?: WorldEntryPendingState | null
  onHandoffChange: (handoff: WorldEntryHandoffState | null) => void
  onPendingHandoffChange?: (pending: WorldEntryPendingState | null) => void
  onOpenAtlas: () => void
  onOpenAtlasReview: (reviewKind: 'entities' | 'relationships' | 'systems') => void
  onWarmAtlas?: () => void
  prominence?: 'prominent' | 'elevated' | 'compact'
}) {
  const { t } = useUiLocale()
  const [worldGenOpen, setWorldGenOpen] = useState(false)
  const emphasized = prominence === 'prominent' || prominence === 'elevated'
  const hasWorldData = worldEntityCount > 0 || worldSystemCount > 0

  const {
    feedback,
    handleBootstrapAccepted,
    handleBootstrapLifecycleChange,
    handleBootstrapTriggerError,
    handleBootstrapTriggerStart,
    handleGenerateSuccess,
    handleImportSuccess,
  } = useWorldEntryLifecycle({
    handoff,
    pending,
    onHandoffChange,
    onPendingHandoffChange,
    t,
  })

  const lifecycleTone = feedback?.phase ?? 'idle'
  const lifecycleAction = feedback?.phase === 'needs_review'
    ? () => onOpenAtlasReview(resolveWorldEntryReviewKind(handoff))
    : onOpenAtlas
  const lifecycleActionLabel =
    feedback?.phase === 'needs_review'
      ? t('studio.worldEntry.handoff.openReview')
      : t('studio.worldEntry.handoff.openAtlas')
  const lifecycleStatusLabel =
    feedback?.phase === 'running'
      ? t('studio.worldEntry.handoff.runningState')
      : feedback?.phase === 'failed'
        ? t('studio.worldEntry.handoff.failedState')
        : feedback?.phase === 'needs_review'
          ? t('studio.worldEntry.handoff.reviewState')
          : feedback?.phase === 'success'
            ? t('studio.worldEntry.handoff.successState')
            : undefined
  const lifecycleTitle =
    feedback?.phase === 'running'
      ? t('studio.worldEntry.handoff.extractRunningTitle')
      : feedback?.phase === 'failed'
        ? t('studio.worldEntry.handoff.extractFailedTitle')
        : feedback?.phase === 'needs_review'
          ? t('studio.worldEntry.handoff.reviewReadyTitle')
          : feedback?.phase === 'success'
            ? t('studio.worldEntry.handoff.syncCompleteTitle')
            : t('studio.rail.atlasTitle')
  const lifecycleDescription =
    feedback?.phase === 'running'
      ? t('studio.worldEntry.handoff.extractRunningDescription')
      : feedback?.phase === 'failed'
        ? t('studio.worldEntry.handoff.extractFailedDescription')
        : feedback?.phase === 'needs_review'
          ? t('studio.worldEntry.handoff.reviewReadyDescription')
          : feedback?.phase === 'success'
            ? t('studio.worldEntry.handoff.syncCompleteDescription')
            : t('studio.worldEntry.reviewHint')
  const lifecycleSummary = feedback?.summary
    ?? (
      hasWorldData
        ? t('studio.worldEntry.summary', {
          entityCount: worldEntityCount,
          systemCount: worldSystemCount,
        })
        : t('studio.worldEntry.summaryEmpty')
    )

  const needsAttention = lifecycleTone !== 'idle'

  return (
    <>
      <section className="space-y-1.5" data-testid="studio-world-entry-panel" data-prominence={prominence}>
        {needsAttention ? (
          <WorldEntryLifecycleCard
            eyebrow="Atlas"
            title={lifecycleTitle}
            description={lifecycleDescription}
            summary={lifecycleSummary}
            tone={lifecycleTone}
            statusLabel={lifecycleStatusLabel}
            actionLabel={lifecycleActionLabel}
            onAction={lifecycleAction}
            onActionWarm={onWarmAtlas}
            actionTestId="studio-world-entry-handoff-action"
            testId="studio-world-entry-handoff"
          />
        ) : (
          <button
            type="button"
            onClick={onOpenAtlas}
            onMouseEnter={onWarmAtlas}
            onFocus={onWarmAtlas}
            className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
            data-testid="studio-world-entry-handoff-action"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
              <Globe className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-foreground">{t('studio.rail.atlasTitle')}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground/80">
                {lifecycleSummary}
              </div>
            </div>
          </button>
        )}

        <button
          type="button"
          onClick={() => setWorldGenOpen(true)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
          data-testid="world-build-generate"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium text-foreground">
              {emphasized ? t('copilot.card.generateFromSettingsLong') : t('copilot.card.generateFromSettings')}
            </div>
          </div>
        </button>

        <div className="px-1" data-testid="world-build-panel">
          <BootstrapPanel
            novelId={novelId}
            variant="sidebar"
            analyticsSource="studio_world_entry_panel"
            onLifecycleChange={handleBootstrapLifecycleChange}
            onTriggerStart={handleBootstrapTriggerStart}
            onTriggerError={handleBootstrapTriggerError}
            onJobAccepted={handleBootstrapAccepted}
          />
        </div>
      </section>

      <WorldGenerationDialog
        novelId={novelId}
        open={worldGenOpen}
        onOpenChange={setWorldGenOpen}
        analyticsSource="studio_world_entry_panel"
        onGenerateSuccess={handleGenerateSuccess}
        onImportSuccess={handleImportSuccess}
        navigateOnGenerateSuccess={false}
        navigateOnImportSuccess={false}
      />
    </>
  )
}
