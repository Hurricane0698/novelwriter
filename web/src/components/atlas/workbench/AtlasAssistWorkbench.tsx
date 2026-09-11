import '@/lib/uiMessagePacks/novel'
import { useCallback, useMemo, useRef, useState, type ReactElement } from 'react'
import { AnimatePresence, domAnimation, LazyMotion, LayoutGroup, m, useReducedMotion } from 'framer-motion'
import { Bot, Globe, Search, Sparkles, X } from 'lucide-react'
import { PanelResizeHandle } from '@/components/novel-shell/PanelResizeHandle'
import { AtlasAssistAttentionBanner } from '@/components/atlas/workbench/AtlasAssistAttentionBanner'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { useOptionalNovelShell } from '@/components/novel-shell/NovelShellContext'
import {
  buildCurrentEntityCopilotLaunchArgs,
  buildDraftCleanupCopilotLaunchArgs,
  buildRelationshipResearchCopilotLaunchArgs,
  buildWholeBookCopilotLaunchArgs,
} from '@/components/novel-copilot/novelCopilotLauncher'
import {
  copilotDrawerShellClassName,
  getCopilotResearchStatusClassName,
} from '@/components/novel-copilot/novelCopilotChrome'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { WorldEntryLifecycleCard } from '@/components/world-model/shared/WorldEntryLifecycleCard'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { useNovelWindowIndex } from '@/hooks/novel/useNovelWindowIndex'
import { useWorldEntryLifecycle } from '@/hooks/world/useWorldEntryLifecycle'
import { useDraftReviewBacklog } from '@/hooks/world/useDraftReviewBacklog'
import {
  resolveAtlasAssistAttentionTone,
  resolveAtlasAssistPresentation,
  resolveWorldEntryReviewKind,
} from '@/lib/worldEntryLifecycle'
import { getWindowIndexCopilotStatusMeta } from '@/lib/windowIndexStatus'
import type {
  AtlasWorkbenchTab,
  WorldEntryHandoffState,
  WorldEntryPendingState,
} from '@/components/novel-shell/NovelShellRouteState'
import type { DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'

export function AtlasAssistWorkbench({
  novelId,
  tab,
  width,
  presentation = 'rail',
  onResize,
  onClose,
  selectedEntityId,
  selectedEntityName,
  worldEntityCount,
  worldSystemCount,
  handoff,
  pending = null,
  onHandoffChange,
  onPendingHandoffChange,
  onOpenDraftReview,
}: {
  novelId: number
  tab: AtlasWorkbenchTab
  width: number
  presentation?: 'rail' | 'overlay'
  onClose?: () => void
  onResize: (nextWidth: number) => void
  selectedEntityId: number | null
  selectedEntityName?: string | null
  worldEntityCount: number
  worldSystemCount: number
  handoff: WorldEntryHandoffState | null
  pending?: WorldEntryPendingState | null
  onHandoffChange: (handoff: WorldEntryHandoffState | null) => void
  onPendingHandoffChange?: (pending: WorldEntryPendingState | null) => void
  onOpenDraftReview: (kind?: DraftReviewKind) => void
}) {
  const { t } = useUiLocale()
  const shell = useOptionalNovelShell()
  const copilot = useNovelCopilot()
  const prefersReducedMotion = useReducedMotion()
  const { data: indexState } = useNovelWindowIndex(novelId)
  const {
    draftEntities,
    draftRelationships,
    draftSystems,
    totalDrafts,
    isResolved: isDraftBacklogResolved,
  } = useDraftReviewBacklog(novelId)
  const [genOpen, setGenOpen] = useState(false)
  const governanceSectionRef = useRef<HTMLElement>(null)

  const indexStatusMeta = getWindowIndexCopilotStatusMeta(indexState)
  const preferredReviewKind: DraftReviewKind =
    tab === 'relationships'
      ? 'relationships'
      : tab === 'systems'
        ? 'systems'
        : 'entities'
  const {
    feedback: governanceFeedback,
    handleBootstrapAccepted,
    handleBootstrapLifecycleChange,
    handleBootstrapTriggerError,
    handleBootstrapTriggerStart,
    handleGenerateSuccess,
    handleImportSuccess,
  } = useWorldEntryLifecycle({
    handoff,
    pending,
    reviewBacklogCount: isDraftBacklogResolved ? totalDrafts : null,
    onHandoffChange,
    onPendingHandoffChange,
    t,
  })

  const contextualAction = useMemo(() => {
    if (tab === 'entities' && selectedEntityId !== null) {
      return {
        title: t('worldModel.atlas.assist.contextEntityTitle'),
        description: t('worldModel.atlas.assist.contextEntityHint'),
        onClick: () => copilot.openDrawer(
          ...buildCurrentEntityCopilotLaunchArgs({
            entityId: selectedEntityId,
            entityName: selectedEntityName,
            surface: 'atlas',
          }),
        ),
      }
    }

    if (tab === 'relationships' && selectedEntityId !== null) {
      return {
        title: t('worldModel.atlas.assist.contextRelationshipTitle'),
        description: t('worldModel.atlas.assist.contextRelationshipHint'),
        onClick: () => copilot.openDrawer(
          ...buildRelationshipResearchCopilotLaunchArgs({
            entityId: selectedEntityId,
            entityName: selectedEntityName,
            surface: 'atlas',
          }),
        ),
      }
    }

    if (tab === 'review') {
      return {
        title: t('worldModel.atlas.assist.contextReviewTitle'),
        description: t('worldModel.atlas.assist.contextReviewHint'),
        onClick: () => copilot.openDrawer(
          ...buildDraftCleanupCopilotLaunchArgs({ surface: 'atlas' }),
        ),
      }
    }

    return null
  }, [copilot, selectedEntityId, selectedEntityName, t, tab])

  const scrollToGovernance = useCallback(() => {
    governanceSectionRef.current?.scrollIntoView({
      block: 'start',
      behavior: 'smooth',
    })
  }, [])

  const queueTone = governanceFeedback?.phase
    ?? (totalDrafts > 0 ? 'needs_review' : 'success')
  const queueStatusLabel =
    queueTone === 'running'
      ? t('worldModel.atlas.assist.runningState')
      : queueTone === 'failed'
        ? t('worldModel.atlas.assist.failedState')
        : queueTone === 'needs_review'
          ? t('worldModel.atlas.assist.reviewState')
          : t('worldModel.atlas.assist.successState')
  const queueTitle =
    queueTone === 'running'
      ? t('worldModel.atlas.assist.runningTitle')
      : queueTone === 'failed'
        ? t('worldModel.atlas.assist.failedTitle')
        : queueTone === 'needs_review'
          ? t('worldModel.atlas.assist.reviewReadyTitle')
          : t('worldModel.atlas.assist.syncedTitle')
  const queueDescription =
    queueTone === 'running'
      ? t('worldModel.atlas.assist.runningDescription')
      : queueTone === 'failed'
        ? t('worldModel.atlas.assist.failedDescription')
        : queueTone === 'needs_review'
          ? (
            totalDrafts > 0
              ? t('worldModel.atlas.assist.queueHint', { count: totalDrafts })
              : t('worldModel.atlas.assist.reviewReadyDescription')
          )
          : t('worldModel.atlas.assist.syncedDescription')
  const queueSummary =
    governanceFeedback?.summary
    ?? t('worldModel.atlas.assist.worldSummary', {
      entityCount: worldEntityCount,
      systemCount: worldSystemCount,
    })
  const showQueueAction = (queueTone === 'needs_review' || totalDrafts > 0) && tab !== 'review'
  const queuedDraftReviewKind: DraftReviewKind =
    draftEntities.length > 0
      ? 'entities'
      : draftRelationships.length > 0
        ? 'relationships'
        : draftSystems.length > 0
          ? 'systems'
          : preferredReviewKind
  const queueReviewKind = governanceFeedback?.phase === 'needs_review'
    ? resolveWorldEntryReviewKind(handoff, queuedDraftReviewKind)
    : queuedDraftReviewKind
  const attentionTone = resolveAtlasAssistAttentionTone({
    tab,
    handoff,
    pending,
    totalDrafts,
    reviewBacklogCount: isDraftBacklogResolved ? totalDrafts : null,
  })
  const {
    stage: assistStage,
    governanceProminence,
    governanceFirst,
  } = resolveAtlasAssistPresentation({
    tab,
    handoff,
    pending,
    totalDrafts,
    reviewBacklogCount: isDraftBacklogResolved ? totalDrafts : null,
  })

  const attentionBanner = assistStage === 'attention' && attentionTone ? (
    <AtlasAssistAttentionBanner
      tone={attentionTone}
      title={
        attentionTone === 'running'
          ? t('worldModel.atlas.assist.attention.runningTitle')
          : attentionTone === 'failed'
            ? t('worldModel.atlas.assist.attention.failedTitle')
            : t('worldModel.atlas.assist.attention.reviewTitle')
      }
      description={
        attentionTone === 'running'
          ? t('worldModel.atlas.assist.attention.runningDescription')
          : attentionTone === 'failed'
            ? t('worldModel.atlas.assist.attention.failedDescription')
            : (
              totalDrafts > 0
                ? t('worldModel.atlas.assist.attention.reviewDescription', { count: totalDrafts })
                : t('worldModel.atlas.assist.reviewReadyDescription')
            )
      }
      actionLabel={
        attentionTone === 'needs_review'
          ? t('worldModel.atlas.assist.openReview')
          : t('worldModel.atlas.assist.attention.showSection')
      }
      onAction={
        attentionTone === 'needs_review'
          ? () => onOpenDraftReview(queueReviewKind)
          : scrollToGovernance
      }
    />
  ) : null

  /* ── Research section: flat button rows ── */
  const researchSection = (
    <section className="space-y-1" data-testid="atlas-assist-research-section">
      <button
        type="button"
        onClick={() => copilot.openDrawer(...buildWholeBookCopilotLaunchArgs(shell?.routeState))}
        className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
        data-testid="atlas-assist-open-whole-book"
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
          <Search className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-foreground">
            {t('worldModel.atlas.assist.wholeBookAction')}
          </div>
          <div className={cn('mt-0.5 text-[11px]', getCopilotResearchStatusClassName(indexStatusMeta.tone))}>
            {indexStatusMeta.text}
          </div>
        </div>
      </button>

      {contextualAction ? (
        <button
          type="button"
          onClick={contextualAction.onClick}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
          data-testid="atlas-assist-context-action"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
            <Bot className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-foreground">
              {contextualAction.title}
            </div>
            <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground/80">
              {contextualAction.description}
            </div>
          </div>
        </button>
      ) : null}
    </section>
  )

  /* ── Governance section: flat button rows + lifecycle card when active ── */
  const bannerOwnsGovernanceAttention = assistStage === 'attention' && attentionTone !== null
  const governanceNeedsAttention = queueTone !== 'success' && !bannerOwnsGovernanceAttention
  const suppressQueueMeta = tab === 'review'
  const governanceSection = (
    <section ref={governanceSectionRef} className="space-y-1" data-testid="atlas-assist-governance-section" data-prominence={governanceProminence}>
      {suppressQueueMeta ? null : governanceNeedsAttention ? (
        <WorldEntryLifecycleCard
          eyebrow={t('worldModel.atlas.assist.governanceEyebrow')}
          title={queueTitle}
          description={queueDescription}
          summary={queueSummary}
          tone={queueTone}
          statusLabel={queueStatusLabel}
          actionLabel={showQueueAction ? t('worldModel.atlas.assist.openReview') : undefined}
          onAction={showQueueAction ? () => onOpenDraftReview(queueReviewKind) : undefined}
          actionTestId="atlas-assist-open-review"
          testId="atlas-assist-queue-meta"
        />
      ) : bannerOwnsGovernanceAttention ? null : (
        <button
          type="button"
          onClick={() => onOpenDraftReview(preferredReviewKind)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
          data-testid="atlas-assist-queue-meta"
          data-tone={queueTone}
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
            <Globe className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium text-foreground">{queueTitle}</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground/80">
              {queueSummary}
            </div>
          </div>
        </button>
      )}

      <button
        type="button"
        onClick={() => setGenOpen(true)}
        className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
        data-testid="atlas-assist-generate"
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-foreground">
            {t('copilot.card.generateFromSettingsLong')}
          </div>
        </div>
      </button>

      <div className="px-1" data-testid="atlas-assist-bootstrap-panel">
        <BootstrapPanel
          novelId={novelId}
          variant="sidebar"
          analyticsSource="atlas_assist_workbench"
          onLifecycleChange={handleBootstrapLifecycleChange}
          onTriggerStart={handleBootstrapTriggerStart}
          onTriggerError={handleBootstrapTriggerError}
          onJobAccepted={handleBootstrapAccepted}
        />
      </div>
    </section>
  )

  const orderedSections: Array<{ key: 'research' | 'governance'; node: ReactElement }> = governanceFirst
    ? [
        { key: 'governance', node: governanceSection },
        { key: 'research', node: researchSection },
      ]
    : [
        { key: 'research', node: researchSection },
        { key: 'governance', node: governanceSection },
      ]

  const layoutTransition = prefersReducedMotion
    ? { duration: 0 }
    : {
        type: 'spring' as const,
        stiffness: 280,
        damping: 28,
        mass: 0.9,
      }
  const bannerTransition = prefersReducedMotion
    ? { duration: 0 }
    : {
        type: 'spring' as const,
        stiffness: 340,
        damping: 30,
        mass: 0.82,
      }

  return (
    <LazyMotion features={domAnimation}>
      <>
      <aside
        className={cn(
          'relative shrink-0 overflow-hidden',
          copilotDrawerShellClassName,
          presentation === 'rail'
            ? 'border-l'
            : 'shadow-xl',
        )}
        style={{
          width,
        }}
        data-testid="atlas-assist-workbench"
        data-presentation={presentation}
      >
        <PanelResizeHandle side="left" width={width} min={280} max={800} onResize={onResize} label={t('copilot.drawer.resize')} />

        <div className="relative flex h-full flex-col">
          <header className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--nw-copilot-border)] px-4 py-3">
            <h2 className="text-sm font-medium">{t('worldModel.atlas.assist.title')}</h2>
            {onClose && <button type="button" onClick={onClose} aria-label={t('copilot.drawer.close')}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-foreground/5"><X className="h-4 w-4" /></button>}
          </header>

          <div
            className="nw-scrollbar-thin flex-1 overflow-y-auto px-3 py-4"
            data-testid="atlas-assist-sections"
            data-stage={assistStage}
          >
            <LayoutGroup id="atlas-assist-workbench-layout">
              <div className="space-y-1">
                <AnimatePresence initial={false}>
                  {attentionBanner ? (
                    <m.div
                      key="atlas-attention-banner"
                      layout
                      initial={prefersReducedMotion ? false : { opacity: 0, y: -12, scale: 0.985 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -12, scale: 0.985 }}
                      transition={bannerTransition}
                    >
                      {attentionBanner}
                    </m.div>
                  ) : null}
                </AnimatePresence>

                {orderedSections.map(({ key, node }) => (
                  <m.div
                    key={key}
                    layout
                    initial={false}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={layoutTransition}
                    style={{ transformOrigin: 'top center' }}
                  >
                    {node}
                  </m.div>
                ))}
              </div>
            </LayoutGroup>
          </div>
        </div>
      </aside>

      <WorldGenerationDialog
        novelId={novelId}
        open={genOpen}
        onOpenChange={setGenOpen}
        analyticsSource="atlas_assist_workbench"
        onGenerateSuccess={handleGenerateSuccess}
        onImportSuccess={handleImportSuccess}
        navigateOnGenerateSuccess={false}
        navigateOnImportSuccess={false}
      />
      </>
    </LazyMotion>
  )
}
