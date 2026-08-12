import type { UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import { isBootstrapStatusRunning, RUNNING_BOOTSTRAP_STATUSES } from '@/lib/bootstrapStatus'
import type { BootstrapJobResponse, BootstrapStatus, Novel } from '@/types/api'

export const STUDIO_BOOTSTRAP_RUNNING_STATUSES: readonly BootstrapStatus[] = RUNNING_BOOTSTRAP_STATUSES

export interface StudioPreparationGateState {
  title: string
  description: string
  detail: string | null
  error: string | null
  primaryActionLabel?: string
  onPrimaryAction?: () => void
  secondaryActionLabel?: string
  onSecondaryAction?: () => void
}

type TranslateFn = (key: UiMessageKey, params?: UiMessageParams) => string

interface ResolveStudioPreparationGateArgs {
  t: TranslateFn
  novelWindowIndex: Novel['window_index'] | null | undefined
  worldLoading: boolean
  worldOnboardingDismissed: boolean
  worldEmpty: boolean
  bootstrapTriggerPending: boolean
  bootstrapJob: BootstrapJobResponse | null | undefined
  bootstrapError: string | null
  onRetryBootstrap: () => void
  onDeferBootstrap: () => void
  onRetryIngest: () => void
  onReturnToLibrary: () => void
}

export function isStudioBootstrapStatusRunning(status: BootstrapStatus | null | undefined): boolean {
  return isBootstrapStatusRunning(status)
}

interface ResolveDeferredAutoBootstrapPendingArgs {
  novelWindowIndex: Novel['window_index'] | null | undefined
  bootstrapJob: BootstrapJobResponse | null | undefined
}

export function isStudioDeferredAutoBootstrapPending({
  novelWindowIndex,
  bootstrapJob,
}: ResolveDeferredAutoBootstrapPendingArgs): boolean {
  const ingestJob = novelWindowIndex?.ingest ?? null
  const chaptersAvailable = novelWindowIndex?.capabilities?.chapters_available ?? false
  const bootstrapAvailable = novelWindowIndex?.capabilities?.bootstrap_available ?? false

  return (
    bootstrapJob == null
    && ingestJob != null
    && ingestJob.status !== 'failed'
    && ingestJob.bootstrap_plan === 'defer_until_index'
    && chaptersAvailable
    && !bootstrapAvailable
  )
}

export function resolveStudioPreparationGate({
  t,
  novelWindowIndex,
  worldLoading,
  worldOnboardingDismissed,
  worldEmpty,
  bootstrapTriggerPending,
  bootstrapJob,
  bootstrapError,
  onRetryBootstrap,
  onDeferBootstrap,
  onRetryIngest,
  onReturnToLibrary,
}: ResolveStudioPreparationGateArgs): StudioPreparationGateState | null {
  const ingestJob = novelWindowIndex?.ingest ?? null
  const chaptersAvailable = novelWindowIndex?.capabilities?.chapters_available ?? false
  const initialBootstrapProducedWorldData = (
    (bootstrapJob?.result.entities_found ?? 0) > 0
    || (bootstrapJob?.result.relationships_found ?? 0) > 0
  )
  const ingestActive = (
    ingestJob !== null
    && (ingestJob.status === 'queued' || ingestJob.status === 'running')
    && !chaptersAvailable
  )
  const initialBootstrapActive = (
    !worldLoading
    && !worldOnboardingDismissed
    && worldEmpty
    && (
      bootstrapTriggerPending
      || (
        bootstrapJob?.mode === 'initial'
        && bootstrapJob.status !== 'failed'
        && isStudioBootstrapStatusRunning(bootstrapJob.status)
      )
    )
  )
  const initialBootstrapFailed = (
    !worldLoading
    && !worldOnboardingDismissed
    && worldEmpty
    && bootstrapJob?.mode === 'initial'
    && bootstrapJob.status === 'failed'
  )
  const initialBootstrapCompletedAwaitingRefresh = (
    !worldLoading
    && !worldOnboardingDismissed
    && worldEmpty
    && bootstrapJob?.mode === 'initial'
    && bootstrapJob.status === 'completed'
    && !bootstrapJob.result.index_refresh_only
    && initialBootstrapProducedWorldData
  )
  const deferredAutoBootstrapPending = (
    !worldLoading
    && !worldOnboardingDismissed
    && worldEmpty
    && isStudioDeferredAutoBootstrapPending({
      novelWindowIndex,
      bootstrapJob,
    })
  )

  const ingestStageLabels: Record<string, string> = {
    accepted: t('studio.preparation.stage.accepted'),
    decoding: t('studio.preparation.stage.decoding'),
    parsing: t('studio.preparation.stage.parsing'),
    planning: t('studio.preparation.stage.planning'),
    persisting: t('studio.preparation.stage.persisting'),
    completed: t('studio.preparation.stage.completed'),
    failed: t('studio.preparation.stage.failed'),
  }
  const bootstrapStageLabels: Partial<Record<BootstrapStatus, string>> = {
    pending: t('worldModel.bootstrap.step.pending'),
    tokenizing: t('worldModel.bootstrap.step.tokenizing'),
    extracting: t('worldModel.bootstrap.step.extracting'),
    windowing: t('worldModel.bootstrap.step.windowing'),
    refining: t('worldModel.bootstrap.step.refining'),
  }

  if (ingestActive) {
    return {
      title: t('studio.preparation.title'),
      description: t('studio.preparation.uploadDescription'),
      detail: ingestStageLabels[ingestJob.stage] ?? t('worldModel.common.processing'),
      error: null,
    }
  }

  if (ingestJob?.status === 'failed' && !chaptersAvailable) {
    if (novelWindowIndex?.readiness === 'failed_retryable') {
      return {
        title: t('studio.preparation.ingestFailedTitle'),
        description: t('studio.preparation.ingestInternalDescription'),
        detail: null,
        error: t('studio.preparation.ingestInternalRepair'),
        primaryActionLabel: t('studio.preparation.retryImport'),
        onPrimaryAction: onRetryIngest,
        secondaryActionLabel: t('studio.preparation.returnLibrary'),
        onSecondaryAction: onReturnToLibrary,
      }
    }

    if (novelWindowIndex?.readiness === 'failed_terminal') {
      let repairKey: UiMessageKey | null = null
      if (ingestJob.error_code === 'source_missing') {
        repairKey = 'studio.preparation.sourceMissingRepair'
      } else if (ingestJob.error_code === 'source_encoding_unsupported') {
        repairKey = 'studio.preparation.encodingRepair'
      } else if (ingestJob.error_code === 'markdown_structure_invalid') {
        repairKey = 'studio.preparation.markdownRepair'
      }

      return {
        title: t('studio.preparation.ingestNeedsFixTitle'),
        description: t('studio.preparation.ingestNeedsFixDescription'),
        detail: null,
        error: repairKey ? t(repairKey) : null,
        primaryActionLabel: t('studio.preparation.returnLibrary'),
        onPrimaryAction: onReturnToLibrary,
      }
    }
  }

  if (initialBootstrapFailed) {
    return {
      title: t('studio.preparation.failedTitle'),
      description: t('studio.preparation.failedDescription'),
      detail: null,
      error: bootstrapError ?? bootstrapJob?.error ?? t('worldModel.error.bootstrapTriggerFailed'),
      primaryActionLabel: t('studio.preparation.retry'),
      onPrimaryAction: onRetryBootstrap,
      secondaryActionLabel: t('studio.preparation.defer'),
      onSecondaryAction: onDeferBootstrap,
    }
  }

  if (initialBootstrapActive) {
    return {
      title: t('studio.preparation.title'),
      description: t('studio.preparation.bootstrapDescription'),
      detail: bootstrapStageLabels[bootstrapJob?.status ?? 'pending'] ?? t('worldModel.common.processing'),
      error: null,
    }
  }

  if (initialBootstrapCompletedAwaitingRefresh) {
    return {
      title: t('studio.preparation.title'),
      description: t('studio.preparation.bootstrapDescription'),
      detail: t('worldModel.common.processing'),
      error: null,
    }
  }

  if (deferredAutoBootstrapPending) {
    return {
      title: t('studio.preparation.title'),
      description: t('studio.preparation.bootstrapDescription'),
      detail: t('worldModel.windowIndex.bootstrap.organizingChapters'),
      error: null,
    }
  }

  return null
}
