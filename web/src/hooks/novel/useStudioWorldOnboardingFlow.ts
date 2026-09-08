import { useCallback, useEffect, useRef, useState } from 'react'
import { LABELS } from '@/constants/labels'
import { isBootstrapInitialized } from '@/lib/bootstrapStatus'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { dismissWorldOnboarding, useWorldOnboardingDismissed } from '@/lib/worldOnboardingStorage'
import { ApiError } from '@/services/api'
import type { UiLocale } from '@/lib/uiMessages'
import type { BootstrapJobResponse, Novel } from '@/types/api'
import {
  isStudioBootstrapStatusRunning,
  isStudioDeferredAutoBootstrapPending,
} from './studioOnboardingPreparation'

interface UseStudioWorldOnboardingFlowArgs {
  novelId: number
  novelCreatedAt?: string | null
  novelWindowIndex?: Novel['window_index'] | null
  locale: UiLocale
  worldEntityCount: number
  worldSystemCount: number
  worldLoading: boolean
  bootstrapLoading: boolean
  bootstrapJob: BootstrapJobResponse | null | undefined
  suppressWorldOnboarding?: boolean
  triggerInitialBootstrap: (handlers?: { onError?: (error: unknown) => void }) => void
  dismissWorldOnboardingRoute: () => void
}

export function useStudioWorldOnboardingFlow({
  novelId,
  novelCreatedAt,
  novelWindowIndex,
  locale,
  worldEntityCount,
  worldSystemCount,
  worldLoading,
  bootstrapLoading,
  bootstrapJob,
  suppressWorldOnboarding = false,
  triggerInitialBootstrap,
  dismissWorldOnboardingRoute,
}: UseStudioWorldOnboardingFlowArgs) {
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const trackedWorldOnboardingViewRef = useRef(false)
  const worldOnboardingDismissed = useWorldOnboardingDismissed(novelId, novelCreatedAt)

  const worldEmpty = worldEntityCount === 0 && worldSystemCount === 0
  const bootstrapRunning = isStudioBootstrapStatusRunning(bootstrapJob?.status)
  const bootstrapAlreadyInitialized = isBootstrapInitialized(bootstrapJob)
  const chaptersAvailable = novelWindowIndex?.capabilities?.chapters_available === true
  const deferredAutoBootstrapPending = isStudioDeferredAutoBootstrapPending({
    novelWindowIndex,
    bootstrapJob,
  })
  // Keep the onboarding hidden while the backend state that governs the
  // Bootstrap button is still unknown (status query in flight) or when the
  // button would 4xx — already-running, already-initialized, or deferred.
  const showWorldOnboarding = (
    !worldLoading
    && !bootstrapLoading
    && !suppressWorldOnboarding
    && !worldOnboardingDismissed
    && worldEmpty
    && !bootstrapRunning
    && !bootstrapAlreadyInitialized
    && !deferredAutoBootstrapPending
  )

  useEffect(() => {
    if (!showWorldOnboarding) {
      trackedWorldOnboardingViewRef.current = false
      return
    }
    if (trackedWorldOnboardingViewRef.current) return
    trackedWorldOnboardingViewRef.current = true
    void trackHostedAnalyticsEvent('world_onboarding_view', {
      novelId,
      meta: { surface: 'studio' },
    })
  }, [novelId, showWorldOnboarding])

  const handleTriggerBootstrap = useCallback(() => {
    // Frontend must not issue requests the backend contract already rejects.
    // See `app/core/world/bootstrap_application.py`: the known 4xx paths are
    //   bootstrap_no_text  — no chapter text to extract
    //   bootstrap_already_running  — a job is in-flight for this novel
    //   bootstrap_initial_mode_not_allowed  — novel was already initialized
    if (bootstrapRunning) {
      setBootstrapError(LABELS.BOOTSTRAP_SCANNING)
      return
    }
    if (bootstrapAlreadyInitialized) {
      setBootstrapError(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
      return
    }
    if (!chaptersAvailable) {
      setBootstrapError(LABELS.BOOTSTRAP_NO_TEXT)
      return
    }

    setBootstrapError(null)
    void trackHostedAnalyticsEvent('bootstrap_trigger', {
      novelId,
      meta: {
        mode: 'initial',
        source_surface: 'world_onboarding',
      },
    })

    triggerInitialBootstrap({
      onError: (err) => {
        void trackHostedAnalyticsEvent('bootstrap_failed', {
          novelId,
          meta: {
            mode: 'initial',
            source_surface: 'world_onboarding',
            status: err instanceof ApiError ? err.status : null,
            error_code: err instanceof ApiError ? err.code ?? null : 'bootstrap_failed',
          },
        })
        if (err instanceof ApiError) {
          const llmMessage = getLlmApiErrorMessage(err, locale)
          if (llmMessage) {
            setBootstrapError(llmMessage)
            return
          }
          if (err.code === 'bootstrap_already_running') {
            setBootstrapError(LABELS.BOOTSTRAP_SCANNING)
            return
          }
          if (err.code === 'bootstrap_no_text') {
            setBootstrapError(LABELS.BOOTSTRAP_NO_TEXT)
            return
          }
        }
        setBootstrapError(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
      },
    })
  }, [
    bootstrapAlreadyInitialized,
    bootstrapRunning,
    chaptersAvailable,
    locale,
    novelId,
    triggerInitialBootstrap,
  ])

  const handleDeferBootstrap = useCallback(() => {
    void trackHostedAnalyticsEvent('world_onboarding_dismissed', {
      novelId,
      meta: { surface: 'studio' },
    })
    dismissWorldOnboarding(novelId, novelCreatedAt)
  }, [novelCreatedAt, novelId])

  const handleDismissWorldOnboarding = useCallback(() => {
    handleDeferBootstrap()
    dismissWorldOnboardingRoute()
  }, [dismissWorldOnboardingRoute, handleDeferBootstrap])

  return {
    bootstrapError,
    chaptersAvailable,
    handleDismissWorldOnboarding,
    handleDeferBootstrap,
    handleTriggerBootstrap,
    showWorldOnboarding,
    worldEmpty,
    worldOnboardingDismissed,
  }
}
