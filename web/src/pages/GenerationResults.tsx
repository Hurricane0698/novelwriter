// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useRef } from 'react'
import { Link, useParams, useNavigate, useLocation } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, Check, RefreshCw, Upload, Info, ChevronDown, ChevronRight, Loader2, Settings, MessageSquarePlus } from 'lucide-react'
import { GlassCard } from '@/components/GlassCard'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import { InjectionSummaryModal } from '@/components/workspace/InjectionSummaryModal'
import { FeedbackForm, type FeedbackAnswers } from '@/components/feedback/FeedbackForm'
import { api, streamContinuation, ApiError } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import { downloadTextFile } from '@/lib/downloadTextFile'
import { cn } from '@/lib/utils'
import type { ContinueDebugSummary, ContinueRequest, ContinueResponse, Continuation } from '@/types/api'

interface VariantState {
  content: string
  continuationId: number | null
  isStreaming: boolean
  error: string | null
}

export function GenerationResults() {
  const { novelId } = useParams<{ novelId: string; chapterNum: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, refreshQuota } = useAuth()
  const state = location.state as {
    streamParams?: ContinueRequest
    novelId?: number
    response?: ContinueResponse
  } | null

  // Legacy mode: response passed directly from old non-streaming path
  const legacyResponse = state?.response
  const legacyVersions: Continuation[] = legacyResponse?.continuations ?? []

  // Reload mode: results restored from URL query (page refresh safe)
  const searchParams = new URLSearchParams(location.search)
  const persisted = searchParams.get('continuations')
  const [persistedVersions, setPersistedVersions] = useState<Continuation[] | null>(null)
  const [persistedError, setPersistedError] = useState<string | null>(null)
  const [reloadAttempt, setReloadAttempt] = useState(0)

  // Capture stream params only on first mount and only when URL does NOT already have persisted IDs.
  // This prevents accidental re-stream (extra LLM cost + duplicate DB rows) when revisiting history entries.
  const initialStreamRef = useRef<
    | {
        novelId: number
        params: ContinueRequest
      }
    | null
    | undefined
  >(undefined)
  if (initialStreamRef.current === undefined) {
    initialStreamRef.current =
      !persisted && state?.streamParams && state?.novelId
        ? { novelId: state.novelId, params: state.streamParams }
        : null
  }
  const streamCtx = initialStreamRef.current

  // Streaming mode state
  const [variants, setVariants] = useState<VariantState[]>([])
  const [activeTab, setActiveTab] = useState(0)
  const [isDone, setIsDone] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isQuotaExhausted, setIsQuotaExhausted] = useState(false)
  const [showFeedbackForm, setShowFeedbackForm] = useState(false)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [streamDebug, setStreamDebug] = useState<ContinueDebugSummary | null>(null)
  const [streamAttempt, setStreamAttempt] = useState(0)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const abortRef = useRef(false)
  const abortCtrlRef = useRef<AbortController | null>(null)
  const continuationMapRef = useRef<Map<number, number>>(new Map())
  const totalVariantsRef = useRef<number>(0)

  const isStreamMode = streamCtx != null
  const nonStreamVersions = persistedVersions ?? legacyVersions
  const isLegacyMode = !isStreamMode && nonStreamVersions.length > 0
  const isReloadMode = !isStreamMode && legacyVersions.length === 0 && !!persisted

  useEffect(() => {
    if (!streamCtx) return

    abortRef.current = false
    abortCtrlRef.current?.abort()
    const ctrl = new AbortController()
    abortCtrlRef.current = ctrl

    continuationMapRef.current = new Map()
    totalVariantsRef.current = 0
    setVariants([])
    setActiveTab(0)
    setIsDone(false)
    setStreamError(null)
    setStreamDebug(null)
    setIsQuotaExhausted(false)
    setShowFeedbackForm(false)

    const consume = async () => {
      try {
        for await (const event of streamContinuation(streamCtx.novelId, streamCtx.params, { signal: ctrl.signal })) {
          if (abortRef.current || ctrl.signal.aborted) break

          switch (event.type) {
            case 'start':
              totalVariantsRef.current = event.total_variants
              if ('debug' in event) setStreamDebug((event as unknown as { debug: ContinueDebugSummary }).debug)
              setVariants(
                Array.from({ length: event.total_variants }, () => ({
                  content: '',
                  continuationId: null,
                  // "Streaming" here means "still in progress" (variant 0 streams tokens, others wait).
                  isStreaming: true,
                  error: null,
                })),
              )
              break

            case 'token':
              setVariants(prev =>
                prev.map((v, i) =>
                  i === event.variant ? { ...v, content: v.content + event.content } : v,
                ),
              )
              break

            case 'variant_done':
              continuationMapRef.current.set(event.variant, event.continuation_id)
              setVariants(prev =>
                prev.map((v, i) =>
                  i === event.variant
                    ? {
                        ...v,
                        content: event.content ?? v.content,
                        continuationId: event.continuation_id,
                        isStreaming: false,
                        error: null,
                      }
                    : v,
                ),
              )
              break

            case 'done': {
              setIsDone(true)
              if ('debug' in event) setStreamDebug((event as unknown as { debug: ContinueDebugSummary }).debug)

              const total = totalVariantsRef.current
              const entries = Array.from(continuationMapRef.current.entries()).sort((a, b) => a[0] - b[0])
              const mapping = entries.map(([v, id]) => `${v}:${id}`).join(',')

              if (mapping && total) {
                const params = new URLSearchParams()
                params.set('continuations', mapping)
                params.set('total_variants', String(total))
                // Persist IDs in URL for refresh, but clear streamParams from history state to avoid re-stream.
                navigate(
                  { pathname: location.pathname, search: params.toString() },
                  { replace: true, state: null },
                )
              }
              break
            }

            case 'error':
              if (event.variant != null) {
                setVariants(prev =>
                  prev.map((v, i) =>
                    i === event.variant!
                      ? { ...v, error: event.message, isStreaming: false }
                      : v,
                  ),
                )
              } else {
                setStreamError(event.message)
              }
              break
          }
        }
      } catch (err) {
        if (abortRef.current || ctrl.signal.aborted) return
        if (err instanceof ApiError && err.status === 429) {
          setIsQuotaExhausted(true)
          setStreamError('生成额度已用完')
        } else if (err instanceof ApiError && err.status === 503) {
          setStreamError('当前使用人数较多，请稍后再试')
        } else {
          setStreamError(err instanceof Error ? err.message : 'Stream failed')
        }
      }
    }

    consume()
    return () => {
      abortRef.current = true
      ctrl.abort()
    }
    // Intentionally only restart the stream when user explicitly retries.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamAttempt])

  useEffect(() => {
    if (!isReloadMode) return
    if (!persisted || !novelId) return

    const pairs = persisted.split(',').map(p => p.trim()).filter(Boolean)
    const byVariant = new Map<number, number>()
    for (const pair of pairs) {
      const [vRaw, idRaw] = pair.split(':')
      const v = parseInt((vRaw || '').trim(), 10)
      const id = parseInt((idRaw || '').trim(), 10)
      if (!Number.isFinite(v) || !Number.isFinite(id)) continue
      byVariant.set(v, id)
    }
    const ids = Array.from(byVariant.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([, id]) => id)
    if (ids.length === 0) {
      setPersistedError('Invalid continuation link')
      return
    }

    setPersistedVersions(null)
    setPersistedError(null)
    api.getContinuations(Number(novelId), ids)
      .then(setPersistedVersions)
      .catch(err => setPersistedError(err instanceof Error ? err.message : 'Failed to load continuations'))
  }, [isReloadMode, persisted, novelId, reloadAttempt])

  // Compute current content for adopt/export
  const currentVariant = isStreamMode ? variants[activeTab] : undefined
  const currentLegacyVersion = isLegacyMode ? nonStreamVersions[activeTab] : undefined
  const currentContent = currentVariant?.content ?? currentLegacyVersion?.content ?? ''
  const allDone = isLegacyMode || isDone
  const tabCount = isStreamMode ? variants.length : nonStreamVersions.length

  const adoptMutation = useMutation({
    mutationFn: () => {
      if (!novelId || !currentContent) {
        throw new Error('No continuation version to adopt')
      }
      return api.createChapter(Number(novelId), {
        content: currentContent,
      })
    },
    onSuccess: () => {
      navigate(`/novel/${novelId}`)
    },
  })

  const handleExportAll = () => {
    if (isStreamMode) {
      if (variants.length === 0) return
      const content = variants
        .map((v, i) => `========== ${'\u7248\u672c'} ${i + 1} ==========\n\n${v.content}\n`)
        .join('\n\n')
      downloadTextFile(`\u7eed\u5199\u7248\u672c_${new Date().toISOString().slice(0, 10)}.txt`, content)
    } else {
      if (nonStreamVersions.length === 0) return
      const content = nonStreamVersions
        .map((v, i) => `========== ${'\u7248\u672c'} ${i + 1} ==========\n\n${v.content}\n`)
        .join('\n\n')
      downloadTextFile(`\u7eed\u5199\u7248\u672c_${new Date().toISOString().slice(0, 10)}.txt`, content)
    }
  }

  const navbarLeftContent = (
    <div className="flex items-center gap-4">
      <Link
        to="/"
        className="font-mono text-lg font-bold text-foreground hover:opacity-80 transition-opacity"
      >
        NovWr
      </Link>
      <span className="text-sm text-muted-foreground">{'\u7eed\u5199\u7ed3\u679c'}</span>
    </div>
  )

  // Show empty/reload state if neither streaming nor legacy data
  if (!isStreamMode && !isLegacyMode) {
    if (isReloadMode && !persistedError && !persistedVersions) {
      return (
        <PageShell
          className="h-screen"
          navbarProps={{
            position: 'static',
            compact: true,
            hideLinks: true,
            leftContent: navbarLeftContent,
          }}
          mainClassName="overflow-hidden"
        >
          <div className="flex flex-1 items-center justify-center flex-col gap-4">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {'\u6b63\u5728\u52a0\u8f7d\u7eed\u5199\u7ed3\u679c...'}
            </span>
          </div>
        </PageShell>
      )
    }

    if (isReloadMode && persistedError) {
      return (
        <PageShell
          className="h-screen"
          navbarProps={{
            position: 'static',
            compact: true,
            hideLinks: true,
            leftContent: navbarLeftContent,
          }}
          mainClassName="overflow-hidden"
        >
          <div className="flex flex-1 items-center justify-center flex-col gap-4">
            <span className="text-sm text-destructive">{persistedError}</span>
            <div className="flex items-center gap-3">
              <NwButton
                onClick={() => setReloadAttempt(v => v + 1)}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                {'\u91cd\u8bd5'}
              </NwButton>
              <NwButton
                onClick={() => navigate(-1)}
                variant="glass"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
              >
                {'\u8fd4\u56de'}
              </NwButton>
            </div>
          </div>
        </PageShell>
      )
    }

    return (
      <PageShell
        className="h-screen"
        navbarProps={{
          position: 'static',
          compact: true,
          hideLinks: true,
          leftContent: navbarLeftContent,
        }}
        mainClassName="overflow-hidden"
      >
        <div className="flex flex-1 items-center justify-center flex-col gap-4">
          <span className="text-sm text-muted-foreground">
            {'\u672a\u627e\u5230\u7eed\u5199\u7ed3\u679c\uff0c\u8bf7\u4ece\u5de5\u4f5c\u533a\u91cd\u65b0\u751f\u6210\u3002'}
          </span>
          <NwButton
            onClick={() => navigate(-1)}
            variant="accent"
            className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
          >
            {'\u8fd4\u56de\u5de5\u4f5c\u533a'}
          </NwButton>
        </div>
      </PageShell>
    )
  }

  // Feedback submit handler for quota-exhausted flow
  const handleFeedbackSubmit = async (answers: FeedbackAnswers) => {
    setFeedbackSubmitting(true)
    try {
      await api.submitFeedback(answers)
      await refreshQuota()
      setShowFeedbackForm(false)
      setIsQuotaExhausted(false)
      setStreamError(null)
      // Auto-retry generation after feedback
      setStreamAttempt(v => v + 1)
    } catch {
      // Could add error handling here
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  // Stream-level error
  if (streamError) {
    return (
      <PageShell
        className="h-screen"
        navbarProps={{
          position: 'static',
          compact: true,
          hideLinks: true,
          leftContent: navbarLeftContent,
        }}
        mainClassName="overflow-hidden"
      >
        <div className="flex flex-1 items-center justify-center flex-col gap-5">
          <span className="text-base font-semibold text-destructive">{streamError}</span>

          {isQuotaExhausted && !user?.feedback_submitted && (
            <div className="flex flex-col items-center gap-3 max-w-md text-center">
              <p className="text-sm text-muted-foreground">
                提交使用反馈即可获得额外生成额度，立即继续创作。
              </p>
              <NwButton
                onClick={() => setShowFeedbackForm(true)}
                variant="accent"
                className="rounded-[10px] px-6 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                <MessageSquarePlus size={16} />
                提交反馈，解锁额度
              </NwButton>
            </div>
          )}

          {isQuotaExhausted && user?.feedback_submitted && (
            <div className="flex flex-col items-center gap-3 max-w-md text-center">
              <p className="text-sm text-muted-foreground">
                反馈额度已领取。你可以在设置中配置自己的 API Key 继续使用。
              </p>
              <NwButton
                onClick={() => navigate('/settings')}
                variant="accent"
                className="rounded-[10px] px-6 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                <Settings size={16} />
                前往设置
              </NwButton>
            </div>
          )}

          {!isQuotaExhausted && (
            <div className="flex items-center gap-3">
              <NwButton
                onClick={() => setStreamAttempt(v => v + 1)}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                重试
              </NwButton>
              <NwButton
                onClick={() => navigate(-1)}
                variant="glass"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
              >
                返回
              </NwButton>
            </div>
          )}

          {isQuotaExhausted && (
            <NwButton
              onClick={() => navigate(-1)}
              variant="glass"
              className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
            >
              返回工作区
            </NwButton>
          )}
        </div>

        {showFeedbackForm && (
          <FeedbackForm
            onSubmit={handleFeedbackSubmit}
            onCancel={() => setShowFeedbackForm(false)}
            submitting={feedbackSubmitting}
          />
        )}
      </PageShell>
    )
  }

  const debug = isStreamMode ? streamDebug : legacyResponse?.debug
  const summary = debug
    ? {
        entities: debug.injected_entities.length,
        relationships: debug.injected_relationships.length,
        systems: debug.injected_systems.length,
      }
    : null

  return (
    <PageShell
      className="h-screen"
      navbarProps={{
        position: 'static',
        compact: true,
        hideLinks: true,
        leftContent: navbarLeftContent,
      }}
      mainClassName="overflow-hidden"
    >
      <div className="flex flex-col flex-1 items-center gap-6 px-8 py-8 lg:px-24 overflow-hidden">
        {tabCount > 0 && (
          <div className="flex items-center">
            {Array.from({ length: tabCount }, (_, i) => {
              const variant = isStreamMode ? variants[i] : undefined
              const isActive = i === activeTab
              const isVariantStreaming = variant?.isStreaming
              const isVariantDone = isLegacyMode || (variant?.continuationId != null)
              const hasError = variant?.error

              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setActiveTab(i)}
                  className={cn(
                    'px-6 py-2.5 text-sm border-b-2 transition-colors flex items-center gap-2',
                    isActive
                      ? 'border-b-accent text-foreground font-semibold'
                      : 'border-b-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {'\u7248\u672c'} {i + 1}
                  {isVariantStreaming && <Loader2 size={14} className="animate-spin" />}
                  {hasError && <span className="text-destructive text-xs">!</span>}
                  {isVariantDone && !isVariantStreaming && !hasError && isStreamMode && (
                    <Check size={14} className="text-green-500" />
                  )}
                </button>
              )
            })}
          </div>
        )}

        <GlassCard className="w-full max-w-[900px] flex-1 overflow-hidden p-10 flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <NwButton
              onClick={() => navigate(-1)}
              variant="glass"
              className="rounded-[10px] px-4 py-2 text-sm font-medium"
            >
              <ArrowLeft size={14} />
              {'\u8fd4\u56de\u5de5\u4f5c\u533a'}
            </NwButton>

            <div className="flex items-center gap-2.5 flex-wrap justify-end">
              <NwButton
                data-testid="results-adopt-button"
                onClick={() => adoptMutation.mutate()}
                disabled={adoptMutation.isPending || !currentContent || !allDone}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)] disabled:cursor-default"
              >
                <Check size={16} />
                {'\u91c7\u7eb3\u6b64\u7248\u672c'}
              </NwButton>

              <NwButton
                onClick={() => navigate(-1)}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <RefreshCw size={14} />
                {'\u91cd\u65b0\u751f\u6210'}
              </NwButton>

              <NwButton
                onClick={handleExportAll}
                disabled={!allDone}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <Upload size={14} />
                {'\u5bfc\u51fa\u5168\u90e8'}
              </NwButton>
            </div>
          </div>

          {/* Content display */}
          {isStreamMode ? (
            !currentVariant ? (
              <div className="flex-1 min-h-0 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : currentVariant.error ? (
              <div className="flex-1 min-h-0 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <span className="text-sm text-destructive">{currentVariant.error}</span>
                  <NwButton
                    onClick={() => setStreamAttempt(v => v + 1)}
                    variant="accent"
                    className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
                  >
                    {'\u91cd\u8bd5'}
                  </NwButton>
                </div>
              </div>
            ) : currentVariant.content ? (
              <PlainTextContent
                content={currentVariant.content}
                className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
                emptyLabel={'\u6682\u65e0\u5185\u5bb9'}
              />
            ) : currentVariant.isStreaming || !currentVariant.continuationId ? (
              <div className="flex-1 min-h-0 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : (
              <PlainTextContent
                content=""
                className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
                emptyLabel={'\u6682\u65e0\u5185\u5bb9'}
              />
            )
          ) : (
            <PlainTextContent
              content={currentLegacyVersion?.content}
              className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
              emptyLabel={'\u6682\u65e0\u5185\u5bb9'}
            />
          )}

          {summary ? (
            <button
              type="button"
              onClick={() => setSummaryOpen(true)}
              className="rounded-[10px] border border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.35)] px-4 py-3 flex items-center justify-between gap-3 text-left transition-colors hover:bg-[hsl(var(--background)/0.45)]"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Info size={14} className="text-muted-foreground" />
                <span className="text-xs text-muted-foreground truncate">
                  {'\u6ce8\u5165\u6458\u8981'}({summary.entities} {'\u4e2a\u5b9e\u4f53'},{summary.relationships} {'\u4e2a\u5173\u7cfb'},{summary.systems} {'\u4e2a\u7cfb\u7edf'})
                </span>
              </div>
              {summaryOpen
                ? <ChevronDown size={14} className="text-muted-foreground shrink-0" />
                : <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              }
            </button>
          ) : null}
        </GlassCard>

        {debug && summaryOpen && (
          <InjectionSummaryModal
            onClose={() => setSummaryOpen(false)}
            debug={debug}
            novelId={novelId!}
          />
        )}
      </div>
    </PageShell>
  )
}
