import type { UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import type { Novel } from '@/types/api'

export interface StudioPreparationGateState {
  title: string
  description: string
  detail: string | null
  error: string | null
  retryable?: boolean
  primaryActionLabel?: string
  secondaryActionLabel?: string
}

type TranslateFn = (key: UiMessageKey, params?: UiMessageParams) => string

interface ResolveStudioPreparationGateArgs {
  t: TranslateFn
  novelWindowIndex: Novel['window_index'] | null | undefined
}

export function resolveStudioPreparationGate({
  t,
  novelWindowIndex,
}: ResolveStudioPreparationGateArgs): StudioPreparationGateState | null {
  const ingestJob = novelWindowIndex?.ingest ?? null
  const chaptersAvailable = novelWindowIndex?.capabilities?.chapters_available ?? false
  if (chaptersAvailable || !ingestJob) return null

  const ingestStageLabels: Record<string, string> = {
    accepted: t('studio.preparation.stage.accepted'),
    decoding: t('studio.preparation.stage.decoding'),
    parsing: t('studio.preparation.stage.parsing'),
    planning: t('studio.preparation.stage.planning'),
    persisting: t('studio.preparation.stage.persisting'),
    completed: t('studio.preparation.stage.completed'),
    failed: t('studio.preparation.stage.failed'),
  }
  if (ingestJob.status === 'queued' || ingestJob.status === 'running') {
    return {
      title: t('studio.preparation.title'),
      description: t('studio.preparation.uploadDescription'),
      detail: ingestStageLabels[ingestJob.stage] ?? t('worldModel.common.processing'),
      error: null,
    }
  }

  if (ingestJob.status === 'failed') {
    if (novelWindowIndex?.readiness === 'failed_retryable') {
      return {
        title: t('studio.preparation.ingestFailedTitle'),
        description: t('studio.preparation.ingestInternalDescription'),
        detail: null,
        error: t('studio.preparation.ingestInternalRepair'),
        primaryActionLabel: t('studio.preparation.retryImport'),
        retryable: true,
        secondaryActionLabel: t('studio.preparation.returnLibrary'),
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
      }
    }
  }

  return null
}
