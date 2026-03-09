import { useEffect, useRef, useState } from 'react'
import { BookOpen, ChevronRight } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { worldKeys } from '@/hooks/world/keys'
import { useToast } from '@/components/world-model/shared/useToast'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { LABELS } from '@/constants/labels'
import { ApiError } from '@/services/api'
import type { BootstrapStatus, BootstrapTriggerRequest } from '@/types/api'

const STEP_LABELS: Record<string, string> = {
  pending: LABELS.BOOTSTRAP_STEP_PENDING,
  tokenizing: LABELS.BOOTSTRAP_STEP_TOKENIZING,
  extracting: LABELS.BOOTSTRAP_STEP_EXTRACTING,
  windowing: LABELS.BOOTSTRAP_STEP_WINDOWING,
  refining: LABELS.BOOTSTRAP_STEP_REFINING,
}

const TOTAL_STEPS = 5

const INITIAL_EXTRACTION_PAYLOAD: BootstrapTriggerRequest = { mode: 'initial' }

const REEXTRACT_PAYLOAD: BootstrapTriggerRequest = {
  mode: 'reextract',
  draft_policy: 'replace_bootstrap_drafts',
  force: true,
}

function isRunning(status: BootstrapStatus): boolean {
  return ['pending', 'tokenizing', 'extracting', 'windowing', 'refining'].includes(status)
}

function isTerminal(status: BootstrapStatus): boolean {
  return status === 'completed' || status === 'failed'
}

type BootstrapPanelVariant = 'sidebar' | 'page'

export function BootstrapPanel({ novelId, variant = 'sidebar' }: { novelId: number; variant?: BootstrapPanelVariant }) {
  const { data: job, isLoading } = useBootstrapStatus(novelId)
  const trigger = useTriggerBootstrap(novelId)
  const { toast } = useToast()
  const qc = useQueryClient()
  const previousStatusRef = useRef<BootstrapStatus | null>(null)
  const [reextractConfirmOpen, setReextractConfirmOpen] = useState(false)
  const initializedFallback = Boolean(
    job && (
      job.mode === 'initial' ||
      job.mode === 'reextract' ||
      (job.status === 'completed' && !job.result.index_refresh_only)
    )
  )
  const isInitialized = Boolean(job?.initialized ?? initializedFallback)

  useEffect(() => {
    const previousStatus = previousStatusRef.current
    const currentStatus = job?.status ?? null
    previousStatusRef.current = currentStatus

    if (!currentStatus || !isTerminal(currentStatus)) return
    if (previousStatus && isTerminal(previousStatus)) return

    qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
    qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
  }, [job?.status, novelId, qc])

  const handleTrigger = (payload: BootstrapTriggerRequest) => {
    trigger.mutate(payload, {
      onError: (err) => {
        if (err instanceof ApiError) {
          const llmMessage = getLlmApiErrorMessage(err)
          if (llmMessage) {
            toast(llmMessage)
            return
          }
          if (err.code === 'bootstrap_already_running') {
            toast(LABELS.BOOTSTRAP_SCANNING)
          } else if (err.code === 'bootstrap_no_text') {
            toast(LABELS.BOOTSTRAP_NO_TEXT)
          } else {
            toast(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
          }
        } else {
          toast(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
        }
      },
    })
  }

  const handleInitialExtraction = () => {
    handleTrigger(INITIAL_EXTRACTION_PAYLOAD)
  }

  const handleReextract = () => {
    setReextractConfirmOpen(true)
  }

  const handleConfirmReextract = () => {
    if (trigger.isPending) return
    setReextractConfirmOpen(false)
    handleTrigger(REEXTRACT_PAYLOAD)
  }

  const reextractConfirmDialog = (
    <ConfirmDialog
      open={reextractConfirmOpen}
      tone="destructive"
      title={LABELS.BOOTSTRAP_REEXTRACT_CONFIRM_TITLE}
      description={LABELS.BOOTSTRAP_REEXTRACT_CONFIRM_DESC}
      confirmText={LABELS.BOOTSTRAP_REEXTRACT_CONFIRM}
      onConfirm={handleConfirmReextract}
      onClose={() => setReextractConfirmOpen(false)}
    />
  )

  // ── Sidebar variant: inline row that lives inside WorldBuildSection card ──
  if (variant === 'sidebar') {
    if (isLoading) {
      return (
        <div className="px-3 py-2.5">
          <div className="h-4 w-32 rounded bg-[hsl(var(--foreground)/0.10)] animate-pulse" />
        </div>
      )
    }

    // Running
    if (job && isRunning(job.status)) {
      const progress = job.progress.step / TOTAL_STEPS
      const stepLabel = STEP_LABELS[job.status] ?? job.progress.detail
      return (
        <div className="px-3 py-2.5 space-y-1.5">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 shrink-0 opacity-70 text-muted-foreground" />
            <span className="text-xs text-muted-foreground flex-1">{stepLabel}</span>
          </div>
          <div className="h-1 rounded-full bg-[hsl(var(--foreground)/0.10)] overflow-hidden">
            <div
              className="h-full rounded-full bg-accent animate-pulse transition-all duration-500"
              style={{ width: `${Math.max(progress * 100, 5)}%` }}
            />
          </div>
        </div>
      )
    }

    // Failed
    if (job?.status === 'failed') {
      return (
        <>
          <button
            type="button"
            onClick={handleInitialExtraction}
            disabled={trigger.isPending}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
          >
            <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
            <span className="flex-1">
              <span className="text-[hsl(var(--color-warning))]">{LABELS.BOOTSTRAP_FAILED}</span>
              {' · 重试'}
            </span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
          </button>
          {reextractConfirmDialog}
        </>
      )
    }

    // Completed
    if (job?.status === 'completed') {
      const short = job.result.index_refresh_only
        ? '索引已刷新'
        : `${job.result.entities_found} 实体 · ${job.result.relationships_found} 关系`
      return (
        <>
          <button
            type="button"
            onClick={handleReextract}
            disabled={trigger.isPending}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
          >
            <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
            <span className="flex-1">
              <span>从章节提取</span>
              <span className="ml-1.5 text-[11px] opacity-70">{short}</span>
            </span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
          </button>
          {reextractConfirmDialog}
        </>
      )
    }

    // Idle (no job)
    return (
      <>
        <button
          type="button"
          onClick={handleInitialExtraction}
          disabled={trigger.isPending}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
        >
          <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
          <span className="flex-1">从章节提取</span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
        </button>
        {reextractConfirmDialog}
      </>
    )
  }

  // ── Page variant: unchanged ──

  const renderPrimaryAction = (primaryVariant: 'default' | 'outline' = 'default') => (
    <div className="flex items-center gap-2 ml-auto">
      {isInitialized ? (
        <Button
          size="sm"
          variant={primaryVariant}
          className="h-7 text-xs text-muted-foreground hover:text-foreground"
          onClick={handleReextract}
          disabled={trigger.isPending}
        >
          {LABELS.BOOTSTRAP_REEXTRACT}
        </Button>
      ) : (
        <Button size="sm" variant={primaryVariant} className="h-7 text-xs" onClick={handleInitialExtraction} disabled={trigger.isPending}>
          {LABELS.BOOTSTRAP_INITIAL_EXTRACTION}
        </Button>
      )}
    </div>
  )

  const shellClass = 'px-4 py-2 border-b border-[var(--nw-glass-border)]'

  if (isLoading) {
    return (
      <div className={shellClass}>
        <div className="h-5 w-40 rounded bg-[hsl(var(--foreground)/0.10)] animate-pulse" />
      </div>
    )
  }

  if (job && isRunning(job.status)) {
    const progress = job.progress.step / TOTAL_STEPS
    const stepLabel = STEP_LABELS[job.status] ?? job.progress.detail
    return (
      <div className={shellClass + ' space-y-1'}>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-1.5 rounded-full bg-[hsl(var(--foreground)/0.10)] overflow-hidden">
            <div
              className="h-full rounded-full bg-accent animate-pulse transition-all duration-500"
              style={{ width: `${Math.max(progress * 100, 5)}%` }}
            />
          </div>
          <Button size="sm" variant="ghost" disabled className="h-7 text-xs">
            {LABELS.BOOTSTRAP_SCANNING}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{stepLabel}</p>
      </div>
    )
  }

  if (job?.status === 'failed') {
    return (
      <>
        <div className={shellClass + ' flex items-center gap-3'}>
          <span className="text-xs text-[hsl(var(--color-warning))]">{LABELS.BOOTSTRAP_FAILED}</span>
          {renderPrimaryAction('outline')}
        </div>
        {reextractConfirmDialog}
      </>
    )
  }

  if (job?.status === 'completed') {
    const completionText = job.result.index_refresh_only
      ? LABELS.BOOTSTRAP_COMPLETED_INDEX_REFRESH
      : LABELS.BOOTSTRAP_COMPLETED_EXTRACTION(job.result.entities_found, job.result.relationships_found)
    return (
      <>
        <div className={shellClass + ' flex items-center gap-3'}>
          <span className="text-xs text-muted-foreground">{completionText}</span>
          {renderPrimaryAction('outline')}
        </div>
        {reextractConfirmDialog}
      </>
    )
  }

  return (
    <>
      <div className={shellClass + ' flex items-center gap-3'}>
        <span className="text-xs text-muted-foreground flex-1" />
        {renderPrimaryAction()}
      </div>
      {reextractConfirmDialog}
    </>
  )
}
