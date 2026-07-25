// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useRef } from 'react'
import '@/lib/uiMessagePacks/novel'
import { NovelShellRail } from '@/components/novel-shell/NovelShellRail'
import {
  StudioResearchPanel,
  type StudioContextualCopilotAction,
} from '@/components/studio/rail/StudioResearchPanel'
import { StudioWorldEntryAttentionBanner } from '@/components/studio/rail/StudioWorldEntryAttentionBanner'
import { StudioWorldEntryPanel } from '@/components/studio/rail/StudioWorldEntryPanel'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { WindowIndexStatusMeta } from '@/lib/windowIndexStatus'
import {
  resolveStudioWorldEntryAttentionTone,
  resolveStudioWorldEntryPresentation,
  resolveWorldEntryReviewKind,
} from '@/lib/worldEntryLifecycle'
import type {
  WorldEntryHandoffState,
  WorldEntryPendingState,
} from '@/components/novel-shell/NovelShellRouteState'
import type { CopilotReviewKind } from '@/types/copilot'

interface StudioSupportRailProps {
  novelId: number
  worldEntityCount: number
  worldSystemCount: number
  windowIndexStatus: WindowIndexStatusMeta
  onOpenWholeBookCopilot: () => void
  worldEntryHandoff: WorldEntryHandoffState | null
  worldEntryPending?: WorldEntryPendingState | null
  onWorldEntryHandoffChange: (handoff: WorldEntryHandoffState | null) => void
  onWorldEntryPendingChange?: (pending: WorldEntryPendingState | null) => void
  onOpenAtlas: () => void
  onOpenAtlasReview: (reviewKind: CopilotReviewKind) => void
  onWarmAtlas?: () => void
  contextualCopilotAction?: StudioContextualCopilotAction
}

export function StudioSupportRail({
  novelId,
  worldEntityCount,
  worldSystemCount,
  windowIndexStatus,
  onOpenWholeBookCopilot,
  worldEntryHandoff,
  worldEntryPending,
  onWorldEntryHandoffChange,
  onWorldEntryPendingChange,
  onOpenAtlas,
  onOpenAtlasReview,
  onWarmAtlas,
  contextualCopilotAction,
}: StudioSupportRailProps) {
  const { t } = useUiLocale()
  const worldEntryPanelRef = useRef<HTMLDivElement>(null)
  const {
    stage: worldEntryStage,
    worldEntryProminence,
  } = resolveStudioWorldEntryPresentation({
    worldEntityCount,
    worldSystemCount,
    handoff: worldEntryHandoff,
    pending: worldEntryPending ?? null,
  })
  const attentionTone = resolveStudioWorldEntryAttentionTone({
    handoff: worldEntryHandoff,
    pending: worldEntryPending ?? null,
  })
  const worldEntryFirst = worldEntryStage !== 'routine'
  const scrollToWorldEntry = useCallback(() => {
    worldEntryPanelRef.current?.scrollIntoView({
      block: 'start',
      behavior: 'smooth',
    })
  }, [])

  const researchPanel = (
    <StudioResearchPanel
      indexStatus={windowIndexStatus}
      onOpenWholeBookCopilot={onOpenWholeBookCopilot}
      contextualCopilotAction={contextualCopilotAction}
    />
  )

  const worldEntryPanel = (
    <div ref={worldEntryPanelRef}>
      <StudioWorldEntryPanel
        novelId={novelId}
        worldEntityCount={worldEntityCount}
        worldSystemCount={worldSystemCount}
        handoff={worldEntryHandoff}
        pending={worldEntryPending ?? null}
        onHandoffChange={onWorldEntryHandoffChange}
        onPendingHandoffChange={onWorldEntryPendingChange}
        onOpenAtlas={onOpenAtlas}
        onOpenAtlasReview={onOpenAtlasReview}
        onWarmAtlas={onWarmAtlas}
        prominence={worldEntryProminence}
      />
    </div>
  )

  const sectionDivider = <div className="mx-3 my-2 h-px bg-[var(--nw-glass-border)]" />

  return (
    <NovelShellRail className="w-[360px] shrink-0 flex flex-col min-h-0 h-full rounded-[16px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-[24px] shadow-[var(--nw-copilot-panel-shadow)] overflow-hidden p-3">
      <div className="flex h-full min-h-0 flex-col gap-3" data-testid="studio-assistant-rail" data-world-entry-stage={worldEntryStage}>
        <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto pr-1" data-testid="studio-support-rail-sections">
          <div className="space-y-1">
            {worldEntryStage === 'attention' && attentionTone ? (
              <StudioWorldEntryAttentionBanner
                tone={attentionTone}
                eyebrow={t('studio.worldEntry.attention.eyebrow')}
                title={
                  attentionTone === 'running'
                    ? t('studio.worldEntry.attention.runningTitle')
                    : attentionTone === 'failed'
                      ? t('studio.worldEntry.attention.failedTitle')
                      : t('studio.worldEntry.attention.reviewTitle')
                }
                description={
                  attentionTone === 'running'
                    ? t('studio.worldEntry.attention.runningDescription')
                    : attentionTone === 'failed'
                      ? t('studio.worldEntry.attention.failedDescription')
                      : t('studio.worldEntry.attention.reviewDescription')
                }
                actionLabel={
                  attentionTone === 'needs_review'
                    ? t('studio.worldEntry.handoff.openReview')
                    : t('studio.worldEntry.attention.showPanel')
                }
                onAction={
                  attentionTone === 'needs_review'
                    ? () => onOpenAtlasReview(resolveWorldEntryReviewKind(worldEntryHandoff))
                    : scrollToWorldEntry
                }
                onActionWarm={attentionTone === 'needs_review' ? onWarmAtlas : undefined}
              />
            ) : null}

            {worldEntryFirst ? (
              <>
                {worldEntryPanel}
                {sectionDivider}
                {researchPanel}
              </>
            ) : (
              <>
                {researchPanel}
                {sectionDivider}
                {worldEntryPanel}
              </>
            )}
          </div>
        </div>
      </div>
    </NovelShellRail>
  )
}
