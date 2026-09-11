import { useEffect, useState, useRef, useCallback } from 'react'
import { PanelResizeHandle } from '@/components/novel-shell/PanelResizeHandle'
import { ArrowLeft, RotateCcw, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getCopilotScopeLabel } from './novelCopilotHelpers'
import { useNovelCopilot } from './NovelCopilotContext'
import type { CopilotSuggestionTarget } from '@/types/copilot'
import {
  useOptionalNovelShell,
} from '@/components/novel-shell/NovelShellContext'
import {
  clampNovelShellDrawerWidth,
  DEFAULT_NOVEL_SHELL_DRAWER_WIDTH,
} from '@/components/novel-shell/novelShellChromeState'
import { NovelCopilotComposer } from './NovelCopilotComposer'
import { NovelCopilotQuickActions } from './NovelCopilotQuickActions'
import { NovelCopilotResearchProcess } from './NovelCopilotResearchProcess'
import { NovelCopilotSuggestionCard } from './NovelCopilotSuggestionCard'
import { AiStatusPill } from './AiStatusPill'
import { NovelCopilotSessionStrip } from './NovelCopilotSessionStrip'
import { getCopilotWorkbenchMeta } from './novelCopilotWorkbench'
import {
  copilotDrawerShellClassName,
  copilotPanelMutedClassName,
  copilotPanelStrongClassName,
  copilotPillInteractiveClassName,
} from './novelCopilotChrome'

const sectionPanelClassName = 'py-1'
const dashedPanelClassName =
  `${copilotPanelMutedClassName} rounded-lg border-dashed px-4 py-4 text-center text-sm text-muted-foreground`

export function NovelCopilotDrawer({
  onLocateTarget,
  onClose,
  onBack,
  width,
  presentation = 'rail',
  overlayTop = 0,
}: {
  novelId: number
  onClose?: () => void
  onBack?: () => void
  width?: number
  presentation?: 'rail' | 'overlay'
  overlayTop?: number
  onLocateTarget?: (target: CopilotSuggestionTarget) => void
}) {
  const {
    isOpen,
    closeDrawer,
    sessions,
    focusedSessionId,
    focusSession,
    removeSession,
    focusedSession,
    activeRun,
    getSessionRun,
    getSessionRuns,
    submitPrompt,
    retryInterruptedRun,
    applySuggestions,
    dismissSuggestions,
  } = useNovelCopilot()
  const shell = useOptionalNovelShell()
  const focusedSessionMeta =
    focusedSessionId == null
      ? null
      : sessions.find((session) => session.sessionId === focusedSessionId) ?? null

  // Keep the drawer cold until there is an actual focused session. This avoids
  // eager world-data fanout on pages that only mount the shell-level drawer.
  if (!isOpen || !focusedSessionMeta) return null

  const activeFocusedSessionId = focusedSessionMeta.sessionId

  return (
    <ActiveNovelCopilotDrawer
      onClose={onClose}
      onBack={onBack}
      width={width}
      presentation={presentation}
      overlayTop={overlayTop}
      onLocateTarget={onLocateTarget}
      shell={shell}
      closeDrawer={closeDrawer}
      sessions={sessions}
      focusedSessionId={activeFocusedSessionId}
      focusSession={focusSession}
      removeSession={removeSession}
      focusedSessionMeta={focusedSessionMeta}
      focusedSession={focusedSession}
      activeRun={activeRun}
      getSessionRun={getSessionRun}
      getSessionRuns={getSessionRuns}
      submitPrompt={submitPrompt}
      retryInterruptedRun={retryInterruptedRun}
      applySuggestions={applySuggestions}
      dismissSuggestions={dismissSuggestions}
    />
  )
}

function ActiveNovelCopilotDrawer({
  onClose,
  onBack,
  width,
  presentation,
  overlayTop,
  onLocateTarget,
  shell,
  closeDrawer,
  sessions,
  focusedSessionId,
  focusSession,
  removeSession,
  focusedSessionMeta,
  focusedSession,
  activeRun,
  getSessionRun,
  getSessionRuns,
  submitPrompt,
  retryInterruptedRun,
  applySuggestions,
  dismissSuggestions,
}: {
  onClose?: () => void
  onBack?: () => void
  width?: number
  presentation: 'rail' | 'overlay'
  overlayTop: number
  onLocateTarget?: (target: CopilotSuggestionTarget) => void
  shell: ReturnType<typeof useOptionalNovelShell>
  closeDrawer: () => void
  sessions: ReturnType<typeof useNovelCopilot>['sessions']
  focusedSessionId: string
  focusSession: ReturnType<typeof useNovelCopilot>['focusSession']
  removeSession: ReturnType<typeof useNovelCopilot>['removeSession']
  focusedSessionMeta: ReturnType<typeof useNovelCopilot>['sessions'][number]
  focusedSession: ReturnType<typeof useNovelCopilot>['focusedSession']
  activeRun: ReturnType<typeof useNovelCopilot>['activeRun']
  getSessionRun: ReturnType<typeof useNovelCopilot>['getSessionRun']
  getSessionRuns: ReturnType<typeof useNovelCopilot>['getSessionRuns']
  submitPrompt: ReturnType<typeof useNovelCopilot>['submitPrompt']
  retryInterruptedRun: ReturnType<typeof useNovelCopilot>['retryInterruptedRun']
  applySuggestions: ReturnType<typeof useNovelCopilot>['applySuggestions']
  dismissSuggestions: ReturnType<typeof useNovelCopilot>['dismissSuggestions']
}) {
  const { locale, t } = useUiLocale()
  const [fallbackDrawerWidth, setFallbackDrawerWidth] = useState(DEFAULT_NOVEL_SHELL_DRAWER_WIDTH)
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null)
  const [applyingSuggestionKeys, setApplyingSuggestionKeys] = useState<Set<string>>(() => new Set())
  const setFallbackDrawerWidthClamped = useCallback((nextWidth: number) => {
    setFallbackDrawerWidth(clampNovelShellDrawerWidth(nextWidth))
  }, [])
  const drawerWidth = shell?.shellState.drawerWidth ?? fallbackDrawerWidth
  const setDrawerWidth = shell?.shellState.setDrawerWidth ?? setFallbackDrawerWidthClamped
  const applyingSuggestionKeysRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') (onClose ?? closeDrawer)()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [closeDrawer, onClose])

  const session = focusedSession ?? focusedSessionMeta
  const workbenchMeta = getCopilotWorkbenchMeta(session.prefill, session.displayTitle, locale)
  const quickActionPrompts = Object.fromEntries(
    workbenchMeta.quickActions.map((action) => [action.id, action.prompt]),
  )

  const handleAction = (action: string) => {
    void submitPrompt(
      session.sessionId,
      quickActionPrompts[action] ?? t('copilot.drawer.fallbackPrompt'),
      session.prefill.scope,
      session.prefill.context,
      action,
    )
  }

  const handleSubmit = (prompt: string) => {
    void submitPrompt(session.sessionId, prompt, session.prefill.scope, session.prefill.context)
  }

  const scopeLabel = getCopilotScopeLabel(session.prefill, locale)
  const sessionRuns = getSessionRuns(session.sessionId)
  const focusedStatus =
    activeRun?.status === 'queued' || activeRun?.status === 'running'
      ? 'running'
      : activeRun?.status === 'error' || activeRun?.status === 'interrupted'
        ? 'error'
        : 'idle'
  const isFocusedSessionBusy = activeRun?.status === 'queued' || activeRun?.status === 'running'

  const handleRetryInterruptedRun = useCallback((runId: string) => {
    if (retryingRunId === runId || isFocusedSessionBusy) return

    setRetryingRunId(runId)
    void retryInterruptedRun(session.sessionId, runId).finally(() => {
      setRetryingRunId((current) => (current === runId ? null : current))
    })
  }, [isFocusedSessionBusy, retryInterruptedRun, retryingRunId, session.sessionId])

  const handleApplySuggestion = useCallback((runId: string, suggestionId: string) => {
    const applyKey = `${session.sessionId}:${runId}:${suggestionId}`
    if (isFocusedSessionBusy || applyingSuggestionKeysRef.current.has(applyKey)) return

    const nextApplying = new Set(applyingSuggestionKeysRef.current)
    nextApplying.add(applyKey)
    applyingSuggestionKeysRef.current = nextApplying
    setApplyingSuggestionKeys(nextApplying)

    void applySuggestions(session.sessionId, runId, [suggestionId]).finally(() => {
      const next = new Set(applyingSuggestionKeysRef.current)
      next.delete(applyKey)
      applyingSuggestionKeysRef.current = next
      setApplyingSuggestionKeys(next)
    })
  }, [applySuggestions, isFocusedSessionBusy, session.sessionId])

  return (
    <>
      <div
        className={cn(
          'nw-copilot-drawer relative shrink-0 flex flex-col overflow-hidden transition-none border-l',
          copilotDrawerShellClassName,
          presentation === 'overlay' && '!absolute bottom-0 right-0 top-0 z-30 shadow-xl'
        )}
        style={{ width: width ?? drawerWidth, ...(presentation === 'overlay' ? { top: overlayTop } : {}) }}
        data-testid="novel-copilot-drawer"
        data-state="open"
        data-presentation={presentation}
        aria-hidden={false}
      >
        <PanelResizeHandle side="left" width={width ?? drawerWidth} min={280} max={800}
          onResize={setDrawerWidth} label={t('copilot.drawer.resize')} />

        <div className="relative flex h-full flex-col">
          <header className="shrink-0 border-b border-[var(--nw-copilot-border)] px-4 py-3">
            <div className="flex items-center gap-2">
              {onClose ? <button type="button" onClick={onBack ?? closeDrawer} aria-label={t('copilot.drawer.back')}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-foreground/5"><ArrowLeft className="h-4 w-4" /></button> : null}
              <h2 className="min-w-0 flex-1 text-sm font-medium">{t('copilot.drawer.badge')}</h2>
              <AiStatusPill status={focusedStatus} />
              <button type="button" onClick={onClose ?? closeDrawer} aria-label={t('copilot.drawer.close')}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-foreground/5 hover:text-foreground"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <span>{scopeLabel}</span>
              {session.displayTitle !== scopeLabel && <><span aria-hidden="true">·</span><span className="truncate">{session.displayTitle}</span></>}
            </div>
          </header>

          <NovelCopilotSessionStrip
            sessions={sessions}
            focusedSessionId={focusedSessionId}
            getSessionStatus={(sessionId) => getSessionRun(sessionId)?.status ?? null}
            onFocusSession={focusSession}
            onRemoveSession={removeSession}
          />

          <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-5" data-testid="copilot-conversation">
            {sessionRuns.length === 0 && (
              <div>
                <p className="text-sm leading-6 text-muted-foreground">{workbenchMeta.introTitle}</p>
                <NovelCopilotQuickActions
                  actions={workbenchMeta.quickActions}
                  onAction={handleAction}
                  disabled={isFocusedSessionBusy}
                />
              </div>
            )}

            {sessionRuns.length > 0 && (
              <div className="animate-in flex flex-col justify-end space-y-4 fade-in slide-in-from-bottom-2 duration-500">
                {sessionRuns.map((run, index) => {
                  const isLatestRun = index === sessionRuns.length - 1
                  const pendingSuggestions = run.suggestions.filter((suggestion) => suggestion.status === 'pending')
                  const appliedSuggestions = run.suggestions.filter((suggestion) => suggestion.status === 'applied')

                  return (
                    <div key={run.run_id} className="space-y-4" data-testid={`copilot-run-${run.run_id}`}>
                      {!isLatestRun && <div className="mx-12 border-t border-[var(--nw-copilot-border)]/60" />}

                      <div className="flex justify-end">
                        <div className={cn(copilotPanelStrongClassName, 'max-w-[88%] rounded-lg px-4 py-3')}>
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/70">
                            {isLatestRun ? t('copilot.drawer.currentRequest') : t('copilot.drawer.previousRequest')}
                          </div>
                          <div className="text-[13px] leading-relaxed text-foreground/95">{run.prompt}</div>
                        </div>
                      </div>

                      {run.status === 'interrupted' && (
                        <div
                          className={cn(
                            copilotPanelMutedClassName,
                            'rounded-lg border-[hsl(var(--color-danger)/0.22)] px-4 py-3 [background:linear-gradient(160deg,hsl(var(--color-danger)/0.08),transparent)]',
                          )}
                        >
                          <div className="flex flex-col gap-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[hsl(var(--color-danger))]/85">
                                  {t('copilot.drawer.interrupted')}
                                </div>
                                <div className="mt-1 text-[13px] leading-relaxed text-[hsl(var(--color-danger))]">
                                  {run.error ?? t('copilot.drawer.interruptedFallback')}
                                </div>
                              </div>
                              {isLatestRun && (
                                <button
                                  type="button"
                                  onClick={() => handleRetryInterruptedRun(run.run_id)}
                                  disabled={isFocusedSessionBusy || retryingRunId === run.run_id}
                                  className={cn(
                                    'inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-[11px] font-medium tracking-[0.01em] text-foreground/85 disabled:cursor-not-allowed disabled:opacity-55',
                                    copilotPillInteractiveClassName,
                                  )}
                                >
                                  <RotateCcw className={cn('h-3.5 w-3.5', retryingRunId === run.run_id && 'animate-spin')} />
                                  {retryingRunId === run.run_id ? t('copilot.drawer.retryingInterrupted') : t('copilot.drawer.retryInterrupted')}
                                </button>
                              )}
                            </div>
                            {isLatestRun && (
                              <div className="flex items-start justify-between gap-3 text-[11px] leading-relaxed text-muted-foreground/72">
                                <span>
                                  {t('copilot.drawer.retryHint')}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {run.status === 'error' && (
                        <div className={cn(dashedPanelClassName, 'border-[hsl(var(--color-danger)/0.22)] text-[hsl(var(--color-danger))] [background:linear-gradient(160deg,hsl(var(--color-danger)/0.08),transparent)]')}>
                          {run.error ?? t('copilot.drawer.errorFallback')}
                        </div>
                      )}

                      {run.status === 'completed' && run.answer && (
                        <div className="py-2">
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/70">
                            {t('copilot.drawer.analysisResult')}
                          </div>
                          <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/90">{run.answer}</div>
                        </div>
                      )}

                      {(run.trace?.length > 0 || run.evidence?.length > 0) && (
                        <NovelCopilotResearchProcess trace={run.trace} evidence={run.evidence} />
                      )}

                      {run.status === 'completed' && pendingSuggestions.length > 0 && (
                        <section className={sectionPanelClassName}>
                          <div className="mb-3 flex items-center justify-between gap-3 px-1">
                            <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/80">
                              {t('copilot.drawer.suggestions')}
                            </h3>
                            <div className="text-[10px] font-medium tracking-[0.05em] text-muted-foreground/60">{t('copilot.drawer.pendingSuggestions', { count: pendingSuggestions.length })}</div>
                          </div>
                          <div className="space-y-3">
                            {pendingSuggestions.map((s) => (
                              <NovelCopilotSuggestionCard
                                key={s.suggestion_id}
                                suggestion={s}
                                isApplying={applyingSuggestionKeys.has(`${session.sessionId}:${run.run_id}:${s.suggestion_id}`)}
                                onApply={(id) => handleApplySuggestion(run.run_id, id)}
                                onDismiss={(id) => void dismissSuggestions(session.sessionId, run.run_id, [id])}
                                onLocateTarget={onLocateTarget}
                              />
                            ))}
                          </div>
                        </section>
                      )}

                      {run.status === 'completed' && appliedSuggestions.length > 0 && (
                        <section className={sectionPanelClassName}>
                          <div className="mb-3 flex items-center justify-between gap-3 px-1">
                            <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] text-foreground/70">
                              {t('copilot.drawer.applied')}
                            </h3>
                            <div className="text-[10px] font-medium tracking-[0.05em] text-muted-foreground/60">{t('copilot.drawer.appliedSuggestions', { count: appliedSuggestions.length })}</div>
                          </div>
                          <div className="space-y-3">
                            {appliedSuggestions.map((s) => (
                              <NovelCopilotSuggestionCard
                                key={s.suggestion_id}
                                suggestion={s}
                                mode="applied"
                                onApply={() => undefined}
                                onDismiss={() => undefined}
                                onLocateTarget={onLocateTarget}
                              />
                            ))}
                          </div>
                        </section>
                      )}

                      {run.status === 'completed' && pendingSuggestions.length === 0 && appliedSuggestions.length === 0 && !run.answer && (
                        <div className={dashedPanelClassName}>{t('copilot.drawer.noSuggestions')}</div>
                      )}

                      {run.status === 'completed' && pendingSuggestions.length === 0 && appliedSuggestions.length > 0 && (
                        <div className={dashedPanelClassName}>
                          {t('copilot.drawer.allHandled')}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="shrink-0 p-3 pt-2">
            <NovelCopilotComposer
              sessionId={session.sessionId}
              onSubmit={handleSubmit}
              disabled={isFocusedSessionBusy}
              label={workbenchMeta.composerLabel}
              placeholder={workbenchMeta.composerPlaceholder}
            />
          </div>
        </div>
      </div>
    </>
  )
}
