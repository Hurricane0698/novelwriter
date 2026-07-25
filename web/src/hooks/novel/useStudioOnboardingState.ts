// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useMemo, useState } from 'react'
import { LABELS } from '@/constants/labels'
import type { UiLocale, UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import type { BootstrapJobResponse, Novel } from '@/types/api'
import {
  resolveStudioPreparationGate,
} from './studioOnboardingPreparation'
import { useStudioWorldOnboardingFlow } from './useStudioWorldOnboardingFlow'

export type { StudioPreparationGateState } from './studioOnboardingPreparation'

type TranslateFn = (key: UiMessageKey, params?: UiMessageParams) => string

interface UseStudioOnboardingStateArgs {
  novelId: number
  novel: Novel | null | undefined
  locale: UiLocale
  t: TranslateFn
  worldEntityCount: number
  worldSystemCount: number
  worldLoading: boolean
  bootstrapLoading: boolean
  bootstrapJob: BootstrapJobResponse | null | undefined
  bootstrapTriggerPending: boolean
  suppressWorldOnboarding?: boolean
  triggerInitialBootstrap: (handlers?: { onError?: (error: unknown) => void }) => void
  dismissWorldOnboardingRoute: () => void
}

export function useStudioOnboardingState({
  novelId,
  novel,
  locale,
  t,
  worldEntityCount,
  worldSystemCount,
  worldLoading,
  bootstrapLoading,
  bootstrapJob,
  bootstrapTriggerPending,
  suppressWorldOnboarding = false,
  triggerInitialBootstrap,
  dismissWorldOnboardingRoute,
}: UseStudioOnboardingStateArgs) {
  const [worldGenOpen, setWorldGenOpen] = useState(false)
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
    handleDismissWorldOnboarding,
    handleTriggerBootstrap,
    preparationGate,
    showWorldOnboarding,
    worldGenOpen,
    setWorldGenOpen,
    worldLoading: worldLoading || bootstrapLoading,
  }
}
