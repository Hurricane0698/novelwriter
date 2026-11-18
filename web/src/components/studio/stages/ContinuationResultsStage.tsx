// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { ChevronDown, ChevronRight, Info } from 'lucide-react'
import { DriftWarningPopover } from '@/components/generation/DriftWarningPopover'
import type { TextAnnotation } from '@/components/ui/annotated-text'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import { useCandidateDraft } from '@/hooks/novel/useCandidateDraft'
import { NwButton } from '@/components/ui/nw-button'
import '@/lib/uiMessagePacks/copilot'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { addToWhitelist, getWhitelist } from '@/lib/postcheckWhitelistStorage'
import { setActiveWarnings } from '@/lib/postcheckActiveWarningsStorage'
import { downloadTextFile } from '@/lib/downloadTextFile'
import { isMarkdownChapterBodyInvalidError } from '@/lib/chapterMutationError'
import { cn } from '@/lib/utils'
import type { ContinueDebugSummary, NovelContentFormat } from '@/types/api'
import {
  ContinuationResultsHeader,
  type ContinuationAdoptErrorCode,
} from './continuation-results/ContinuationResultsHeader'
import { ContinuationResultsPane } from './continuation-results/ContinuationResultsPane'
import {
  ContinuationResultsEmptyState,
  ContinuationResultsLoadingState,
  ContinuationResultsReloadErrorState,
} from './continuation-results/ContinuationResultsStates'
import { ContinuationResultsTabs } from './continuation-results/ContinuationResultsTabs'
import {
  resolveDriftWarnings,
  resolveProseWarnings,
  resolveResultsDebug,
} from './continuation-results/helpers'
import { useContinuationResultsSource } from './continuation-results/useContinuationResultsSource'

export function ContinuationResultsStage({
  novelId,
  contentFormat,
  isActive,
  activeChapterNum,
  activeChapterReference,
  showInjectionSummaryRail,
  onToggleInjectionSummaryRail,
  onDebugChange,
  assistOpen,
  onToggleAssist,
}: {
  novelId: number
  contentFormat: NovelContentFormat
  isActive: boolean
  activeChapterNum: number | null
  activeChapterReference?: string | null
  showInjectionSummaryRail: boolean
  onToggleInjectionSummaryRail: () => void
  onDebugChange: (debug: ContinueDebugSummary | null) => void
  assistOpen?: boolean
  onToggleAssist?: () => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { locale, t } = useUiLocale()
  const [activeTab, setActiveTab] = useState(0)
  const [whitelist, setWhitelist] = useState<string[]>(() => getWhitelist(novelId))
  const [adoptError, setAdoptError] = useState<{
    sourceIdentity: string
    activeTab: number
    candidateId: number | null
    content: string
    code: ContinuationAdoptErrorCode
  } | null>(null)
  const adoptRequestGenerationRef = useRef(0)
  const createChapter = useCreateChapter(novelId)

  const {
    sourceIdentity,
    locationState,
    legacyResponse,
    variants,
    fallbackNotice,
    fallbackVersions,
    nonStreamVersions,
    persistedDebug,
    persistedError,
    reloadedWarnings,
    streamDebug,
    streamError,
    isDone,
    isStreamMode,
    isFallbackMode,
    isLegacyMode,
    isReloadMode,
    retryStream,
    retryReload,
  } = useContinuationResultsSource({
    novelId,
    activeChapterNum,
    location,
    navigate,
    locale,
    t,
  })

  const semanticSourceIdentity = `${novelId}:${activeChapterNum ?? 'none'}:${sourceIdentity}`
  const sourceSessionRef = useRef({
    isActive,
    sourceIdentity: semanticSourceIdentity,
    generation: 0,
  })
  useLayoutEffect(() => {
    const currentSession = sourceSessionRef.current
    if (
      currentSession.isActive === isActive
      && currentSession.sourceIdentity === semanticSourceIdentity
    ) {
      return
    }
    sourceSessionRef.current = {
      isActive,
      sourceIdentity: semanticSourceIdentity,
      generation: currentSession.generation + 1,
    }
    adoptRequestGenerationRef.current += 1
  }, [isActive, semanticSourceIdentity])

  const handleDismissTerm = useCallback((term: string) => {
    addToWhitelist(novelId, term)
    setWhitelist((prev) => [...prev, term])
  }, [novelId])

  const driftWarnings = useMemo(() => resolveDriftWarnings({
    isStreamMode,
    isDone,
    streamDebug,
    legacyDebug: legacyResponse?.debug,
    reloadedWarnings,
  }), [isDone, isStreamMode, legacyResponse?.debug, reloadedWarnings, streamDebug])

  const driftAnnotations: TextAnnotation[] = useMemo(() => {
    if (driftWarnings.length === 0) return []

    const targetVersion = activeTab + 1
    return driftWarnings
      .filter((warning) => (warning.version == null || warning.version === targetVersion) && !whitelist.includes(warning.term))
      .map((warning) => ({
        id: `drift-${warning.code}-${warning.term}`,
        term: warning.term,
        className: 'nw-drift-highlight',
        renderPopover: ({ onClose }: { onClose: () => void }) => (
          <DriftWarningPopover
            code={warning.code}
            term={warning.term}
            onDismiss={() => {
              handleDismissTerm(warning.term)
              onClose()
            }}
          />
        ),
      }))
  }, [activeTab, driftWarnings, handleDismissTerm, whitelist])

  const resultsKey = [semanticSourceIdentity, isFallbackMode, isStreamMode, isLegacyMode, isReloadMode, variants.length].join(':')
  const [previous, setPrevious] = useState({ resultsKey, isActive })
  if (previous.resultsKey !== resultsKey || previous.isActive !== isActive) {
    setPrevious({ resultsKey, isActive })
    setAdoptError(null)
    if (previous.resultsKey !== resultsKey) setActiveTab(0)
  }
  useLayoutEffect(() => {
    adoptRequestGenerationRef.current += 1
  }, [resultsKey])

  const currentVariant = isStreamMode && !isFallbackMode ? variants[activeTab] : undefined
  const currentLegacyVersion = isFallbackMode
    ? fallbackVersions[activeTab]
    : (isLegacyMode ? nonStreamVersions[activeTab] : undefined)
  const currentCandidateId = currentVariant?.continuationId ?? currentLegacyVersion?.id ?? null
  const allDone = isLegacyMode || isFallbackMode || isDone
  const draft = useCandidateDraft({ novelId, candidateId: currentCandidateId,
    original: currentVariant?.content ?? currentLegacyVersion?.content ?? '', initial: currentLegacyVersion,
    enabled: isActive && allDone,
  })
  const currentContent = draft.content
  const currentCandidateIdentity = `${semanticSourceIdentity}:${activeTab}:${currentCandidateId ?? 'pending'}`
  const currentCandidateIdentityRef = useRef(currentCandidateIdentity)
  useLayoutEffect(() => {
    currentCandidateIdentityRef.current = currentCandidateIdentity
  }, [currentCandidateIdentity])
  const adoptErrorCode = (
    isActive
    && adoptError?.sourceIdentity === semanticSourceIdentity
    && adoptError.activeTab === activeTab
    && adoptError.candidateId === currentCandidateId
    && adoptError.content === currentContent
  )
    ? adoptError.code
    : null
  const tabCount = isStreamMode && !isFallbackMode ? variants.length : (isFallbackMode ? fallbackVersions.length : nonStreamVersions.length)

  const debug = resolveResultsDebug({
    isStreamMode,
    streamDebug,
    legacyDebug: legacyResponse?.debug,
    persistedDebug,
    studioResultsDebug: locationState?.studioResultsDebug ?? null,
  })
  const summary = debug
    ? {
        entities: debug.injected_entities.length,
        relationships: debug.injected_relationships.length,
        systems: debug.injected_systems.length,
        recaps: debug.injected_context_summaries.length,
      }
    : null

  useEffect(() => {
    onDebugChange(debug)
  }, [debug, onDebugChange])

  const leaveResults = useCallback((target: string) => {
    const currentSession = sourceSessionRef.current
    sourceSessionRef.current = {
      ...currentSession,
      isActive: false,
      generation: currentSession.generation + 1,
    }
    adoptRequestGenerationRef.current += 1
    setAdoptError(null)
    navigate(target, { state: null })
  }, [navigate])

  const handleAdopt = useCallback(() => {
    if (!isActive || !currentContent) return
    const requestGeneration = adoptRequestGenerationRef.current + 1
    adoptRequestGenerationRef.current = requestGeneration
    const requestCandidateIdentity = currentCandidateIdentity
    const requestSourceSession = sourceSessionRef.current
    setAdoptError(null)
    createChapter.mutate(
      { content: currentContent },
      {
        onSuccess: (chapter) => {
          // Creation is already committed server-side. Preserve the confirmation
          // flow across tab changes, but never navigate from an abandoned result source.
          const currentSourceSession = sourceSessionRef.current
          if (
            !currentSourceSession.isActive
            || currentSourceSession.sourceIdentity !== requestSourceSession.sourceIdentity
            || currentSourceSession.generation !== requestSourceSession.generation
          ) {
            return
          }
          const currentDebug = resolveResultsDebug({
            isStreamMode,
            streamDebug,
            legacyDebug: legacyResponse?.debug,
            persistedDebug,
            studioResultsDebug: locationState?.studioResultsDebug ?? null,
          })
          const allWarnings = currentDebug?.drift_warnings ?? (reloadedWarnings.length > 0 ? reloadedWarnings : undefined)
          if (allWarnings?.length) {
            const targetVersion = activeTab + 1
            const activeWarnings = allWarnings.filter(
              (warning) => (warning.version == null || warning.version === targetVersion) && !whitelist.includes(warning.term),
            )
            if (activeWarnings.length > 0) {
              setActiveWarnings(novelId, chapter.chapter_number, activeWarnings, chapter.created_at)
            }
          }
          navigate(`/novel/${novelId}?chapter=${chapter.chapter_number}`, { state: null })
        },
        onError: (error) => {
          const currentSourceSession = sourceSessionRef.current
          if (
            adoptRequestGenerationRef.current !== requestGeneration
            || currentCandidateIdentityRef.current !== requestCandidateIdentity
            || !currentSourceSession.isActive
            || currentSourceSession.sourceIdentity !== requestSourceSession.sourceIdentity
            || currentSourceSession.generation !== requestSourceSession.generation
          ) {
            return
          }
          setAdoptError({
            sourceIdentity: semanticSourceIdentity,
            activeTab,
            candidateId: currentCandidateId,
            content: currentContent,
            code: isMarkdownChapterBodyInvalidError(error) ? error.code : 'chapter_adopt_failed',
          })
        },
      },
    )
  }, [
    activeTab,
    createChapter,
    currentCandidateId,
    currentCandidateIdentity,
    currentContent,
    isActive,
    isStreamMode,
    legacyResponse?.debug,
    locationState?.studioResultsDebug,
    navigate,
    novelId,
    persistedDebug,
    reloadedWarnings,
    semanticSourceIdentity,
    streamDebug,
    whitelist,
  ])

  const handleExportAll = useCallback(() => {
    const versions = isStreamMode && !isFallbackMode
      ? variants
      : (isFallbackMode ? fallbackVersions : nonStreamVersions)
    if (versions.length === 0) return
    const content = versions
      .map((variant, index) => `${t('continuation.results.exportVersionHeader', { n: index + 1 })}\n\n${variant.content}\n`)
      .join('\n\n')
    downloadTextFile(
      `continuation_versions_${new Date().toISOString().slice(0, 10)}.txt`,
      content,
      'text/plain;charset=utf-8',
    )
  }, [fallbackVersions, isFallbackMode, isStreamMode, nonStreamVersions, t, variants])

  const proseWarnings = useMemo(() => {
    const targetVersion = activeTab + 1
    return resolveProseWarnings({
      isStreamMode,
      isFallbackMode,
      isDone,
      streamDebug,
      legacyDebug: legacyResponse?.debug,
      persistedDebug,
      studioResultsDebug: locationState?.studioResultsDebug ?? null,
    }).filter((warning) => warning.version == null || warning.version === targetVersion)
  }, [
    activeTab,
    isDone,
    isFallbackMode,
    isStreamMode,
    legacyResponse?.debug,
    locationState?.studioResultsDebug,
    persistedDebug,
    streamDebug,
  ])

  if (!isStreamMode && !isLegacyMode) {
    if (isReloadMode && !persistedError && nonStreamVersions.length === 0) {
      return <ContinuationResultsLoadingState label={t('continuation.results.loading')} />
    }

    if (isReloadMode && persistedError) {
      return (
        <ContinuationResultsReloadErrorState
          error={persistedError}
          onRetry={retryReload}
          onBack={() => leaveResults(`/novel/${novelId}`)}
          t={t}
        />
      )
    }

    return (
      <ContinuationResultsEmptyState
        onBack={() => leaveResults(`/novel/${novelId}`)}
        t={t}
      />
    )
  }

  if (streamError) {
    return (
      <ContinuationResultsReloadErrorState
        error={streamError}
        onRetry={retryStream}
        onBack={() => leaveResults(`/novel/${novelId}?stage=write`)}
        t={t}
      />
    )
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col gap-5 px-8 py-6 lg:px-12 overflow-hidden">
      <ContinuationResultsHeader
        activeChapterNum={activeChapterNum}
        activeChapterReference={activeChapterReference}
        fallbackNotice={fallbackNotice}
        isStreamMode={isStreamMode}
        isDone={isDone}
        currentContent={currentContent}
        allDone={allDone}
        adoptEdited={draft.edited}
        createPending={createChapter.isPending || draft.busy}
        adoptErrorCode={adoptErrorCode}
        onAdopt={() => {
          if (draft.busy) return
          if (!draft.ready) { handleAdopt(); return }
          const identity = currentCandidateIdentity
          void draft.flush().then(() => {
            if (currentCandidateIdentityRef.current === identity && sourceSessionRef.current.isActive) handleAdopt()
          }).catch(() => undefined)
        }}
        onBackToWrite={() => leaveResults(`/novel/${novelId}?stage=write`)}
        onExportAll={handleExportAll}
        assistOpen={assistOpen}
        onToggleAssist={onToggleAssist}
        t={t}
      />

      <ContinuationResultsTabs
        tabCount={tabCount}
        activeTab={activeTab}
        isStreamMode={isStreamMode}
        isFallbackMode={isFallbackMode}
        isLegacyMode={isLegacyMode}
        variants={variants}
        onSelect={(tab) => {
          adoptRequestGenerationRef.current += 1
          setAdoptError(null)
          setActiveTab(tab)
        }}
        t={t}
      />

      {draft.ready && <div className="flex flex-wrap items-center gap-2 border-b border-border/50 pb-3">
        {(['original', 'current'] as const).map((view) => <NwButton key={view} variant={draft.view === view ? 'accentOutline' : 'ghost'}
          className="rounded-lg px-3 py-1.5 text-xs" disabled={draft.busy} onClick={() => draft.setView(view)}>
          {t(view === 'original' ? 'review.original' : 'review.current')}</NwButton>)}
        <NwButton variant="glass" className="rounded-lg px-3 py-1.5 text-xs" disabled={draft.busy}
          onClick={() => draft.setView('edit')}>{t('review.edit')}</NwButton>
        {draft.view === 'edit' && <NwButton variant="accentOutline" className="rounded-lg px-3 py-1.5 text-xs"
          disabled={draft.busy} onClick={() => void draft.flush().then(() => draft.setView('current')).catch(() => undefined)}>
          {t(draft.saving ? 'review.saving' : 'review.save')}</NwButton>}
        <NwButton variant="glass" className="ml-auto rounded-lg px-3 py-1.5 text-xs" disabled={draft.busy}
          title={t('review.openHint')} onClick={draft.openReview}>{t('review.candidate')}</NwButton>
      </div>}
      {draft.error && <p role="alert" className="text-xs text-destructive">{draft.error}</p>}
      {draft.edited && <p className="text-xs text-muted-foreground">{t(draft.unsaved ? 'review.unsaved' : 'review.saved')}</p>}

      {draft.view === 'edit' && draft.ready ? <textarea aria-label={t('review.current')} data-testid="candidate-draft-editor"
        value={currentContent} onChange={(event) => draft.change(event.target.value)} readOnly={draft.busy}
        className="min-h-0 flex-1 w-full resize-none bg-transparent px-4 py-4 text-[15px] leading-[2] outline-none nw-scrollbar-thin" /> : <ContinuationResultsPane
        contentFormat={contentFormat}
        isStreamMode={isStreamMode}
        isFallbackMode={isFallbackMode}
        currentVariant={currentVariant ? { ...currentVariant, content: draft.view === 'original' ? draft.original : currentContent } : undefined}
        currentLegacyVersion={currentLegacyVersion ? { ...currentLegacyVersion, content: draft.view === 'original' ? draft.original : currentContent } : undefined}
        driftAnnotations={driftAnnotations}
        proseWarnings={proseWarnings}
        onRetryStream={retryStream}
        t={t}
      />}

      {summary ? (
        <button
          type="button"
          onClick={onToggleInjectionSummaryRail}
          aria-expanded={showInjectionSummaryRail}
          className={cn(
            'shrink-0 rounded-[10px] border px-4 py-3 flex items-center justify-between gap-3 text-left transition-colors',
            showInjectionSummaryRail
              ? 'border-[hsl(var(--accent)/0.3)] bg-[hsl(var(--accent)/0.06)]'
              : 'border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.35)] hover:bg-[hsl(var(--background)/0.45)]',
          )}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Info size={14} className={showInjectionSummaryRail ? 'text-accent' : 'text-muted-foreground'} />
            <span className={cn('text-xs truncate', showInjectionSummaryRail ? 'text-accent' : 'text-muted-foreground')}>
              {t('continuation.results.injectionSummary', {
                entities: summary.entities,
                relationships: summary.relationships,
                systems: summary.systems,
                recaps: summary.recaps,
              })}
            </span>
          </div>
          {showInjectionSummaryRail ? (
            <ChevronDown size={14} className="text-accent shrink-0" />
          ) : (
            <ChevronRight size={14} className="text-muted-foreground shrink-0" />
          )}
        </button>
      ) : null}
    </div>
  )
}
