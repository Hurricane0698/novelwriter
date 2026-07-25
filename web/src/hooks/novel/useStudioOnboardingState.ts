// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useMemo, useState } from 'react'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'
import { LABELS } from '@/constants/labels'
import type { UiLocale, UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import {
  countVisitedDemoFirstWritingOnboardingSteps,
} from '@/lib/demoFirstOnboardingStorage'
import { isSeededDemoNovel } from '@/lib/demoProject'
import type { BootstrapJobResponse, Novel } from '@/types/api'
import {
  resolveStudioPreparationGate,
} from './studioOnboardingPreparation'
import { resolveStudioDemoGuideVisibility } from './studioDemoGuideState'
import { useDemoFirstGuideStorageState } from './useDemoFirstGuideStorageState'
import { useDemoFirstGuideAnalytics } from './useDemoFirstGuideAnalytics'
import { useStudioDemoGuideActions } from './useStudioDemoGuideActions'
import { useStudioWorldOnboardingFlow } from './useStudioWorldOnboardingFlow'

export type { StudioPreparationGateState } from './studioOnboardingPreparation'

type TranslateFn = (key: UiMessageKey, params?: UiMessageParams) => string

interface UseStudioOnboardingStateArgs {
  novelId: number
  novel: Novel | null | undefined
  locale: UiLocale
  t: TranslateFn
  searchParams: URLSearchParams
  activeStage: NovelShellStage
  activeChapterNum: number | null
  chapterLoading: boolean
  showWorkbenchRail: boolean
  worldEntityCount: number
  worldSystemCount: number
  worldLoading: boolean
  bootstrapLoading: boolean
  bootstrapJob: BootstrapJobResponse | null | undefined
  bootstrapTriggerPending: boolean
  suppressWorldOnboarding?: boolean
  triggerInitialBootstrap: (handlers?: { onError?: (error: unknown) => void }) => void
  openDemoChapter: () => void
  openDemoWriteStage: () => void
  openDemoAtlas: () => void
  openDemoCopilot: () => void
  dismissWorldOnboardingRoute: () => void
}

export function useStudioOnboardingState({
  novelId,
  novel,
  locale,
  t,
  searchParams,
  activeStage,
  activeChapterNum,
  chapterLoading,
  showWorkbenchRail,
  worldEntityCount,
  worldSystemCount,
  worldLoading,
  bootstrapLoading,
  bootstrapJob,
  bootstrapTriggerPending,
  suppressWorldOnboarding = false,
  triggerInitialBootstrap,
  openDemoChapter,
  openDemoWriteStage,
  openDemoAtlas,
  openDemoCopilot,
  dismissWorldOnboardingRoute,
}: UseStudioOnboardingStateArgs) {
  const isDemoNovel = isSeededDemoNovel(novel)
  const [worldGenOpen, setWorldGenOpen] = useState(false)
  const {
    demoGuideStorageKey,
    demoGuideState,
    manualForceOpenDemoGuide,
    markStepVisited,
    skipDemoGuide,
    openManualDemoGuide,
    closeManualDemoGuide,
  } = useDemoFirstGuideStorageState({
    novelId,
    createdAt: novel?.created_at,
  })
  const {
    bootstrapError,
    chaptersAvailable,
    handleDismissWorldOnboarding,
    handleTriggerBootstrap,
    showWorldOnboarding,
    worldEmpty,
    worldOnboardingDismissed,
  } = useStudioWorldOnboardingFlow({
    novelId,
    novelCreatedAt: novel?.created_at,
    novelWindowIndex: novel?.window_index,
    locale,
    worldEntityCount,
    worldSystemCount,
    worldLoading,
    bootstrapLoading,
    bootstrapJob,
    suppressWorldOnboarding,
    triggerInitialBootstrap,
    dismissWorldOnboardingRoute,
  })

  const {
    forceOpenDemoGuide,
    showDemoGuideExpanded,
    showDemoGuideReopen,
  } = resolveStudioDemoGuideVisibility({
    demoGuideSearchParam: searchParams.get('demoGuide'),
    manualForceOpenDemoGuide,
    showWorldOnboarding,
    isDemoNovel,
    demoGuideState,
  })
  const demoGuideProgressCount = countVisitedDemoFirstWritingOnboardingSteps(demoGuideState)

  const {
    visitDemoGuideStep,
    handleSkipDemoGuide,
  } = useDemoFirstGuideAnalytics({
    novelId,
    isDemoNovel,
    demoGuideStorageKey,
    demoGuideState,
    demoGuideProgressCount,
    forceOpenDemoGuide,
    showDemoGuideExpanded,
    activeStage,
    activeChapterNum,
    chapterLoading,
    showWorkbenchRail,
    markStepVisited,
    skipDemoGuide,
    closeManualDemoGuide,
  })

  const {
    handleReopenDemoGuide,
    handleOpenDemoChapter,
    handleOpenDemoWriteStage,
    handleOpenDemoAtlas,
    handleOpenDemoCopilot,
  } = useStudioDemoGuideActions({
    visitDemoGuideStep,
    openManualDemoGuide,
    openDemoChapter,
    openDemoWriteStage,
    openDemoAtlas,
    openDemoCopilot,
  })
  const preparationGate = useMemo(() => resolveStudioPreparationGate({
    t,
    novelWindowIndex: novel?.window_index,
    worldLoading,
    worldOnboardingDismissed,
    worldEmpty,
    bootstrapTriggerPending,
    bootstrapJob,
    bootstrapError: bootstrapError ?? bootstrapJob?.error ?? LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED,
    onRetryBootstrap: handleTriggerBootstrap,
    onDeferBootstrap: handleDismissWorldOnboarding,
  }), [
    bootstrapError,
    bootstrapJob,
    bootstrapTriggerPending,
    handleDismissWorldOnboarding,
    handleTriggerBootstrap,
    novel?.window_index,
    t,
    worldEmpty,
    worldLoading,
    worldOnboardingDismissed,
  ])

  return {
    bootstrapError,
    bootstrapTriggerPending,
    chaptersAvailable,
    demoGuideProgressCount,
    demoGuideState,
    handleDismissWorldOnboarding,
    handleOpenDemoAtlas,
    handleOpenDemoChapter,
    handleOpenDemoCopilot,
    handleOpenDemoWriteStage,
    handleReopenDemoGuide,
    handleSkipDemoGuide,
    handleTriggerBootstrap,
    isDemoNovel,
    preparationGate,
    showDemoGuideExpanded,
    showDemoGuideReopen,
    showWorldOnboarding,
    worldGenOpen,
    setWorldGenOpen,
    worldLoading: worldLoading || bootstrapLoading,
  }
}
