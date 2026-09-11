// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useMemo, useState } from 'react'
import type { Location, NavigateFunction } from 'react-router-dom'
import {
  readNovelShellArtifactPanelSearchParams,
  readResultsProvenanceSearchParams,
  setNovelShellArtifactPanelSearchParams,
  setResultsProvenanceSearchParams,
  type AtlasStudioOriginState,
  type NovelShellArtifactPanelState,
  type NovelShellRouteState,
  type NovelShellStage,
  type ResultsProvenance,
} from '@/components/novel-shell/NovelShellRouteState'
import { readGenerationResultsDebug } from '@/lib/generationResultsDebugStorage'
import {
  pickInitialInjectionSummaryCategory,
  type InjectionSummaryCategory,
} from '@/lib/injectionSummaryNavigation'
import type { ContinueDebugSummary } from '@/types/api'

interface StudioResultsLocationState {
  streamParams?: unknown
  novelId?: number
  studioResultsDebug?: ContinueDebugSummary | null
}

interface UseStudioArtifactStateArgs {
  novelId: number
  activeStage: NovelShellStage
  activeChapterNum: number | null
  routeState: Pick<NovelShellRouteState, 'entityId' | 'systemId' | 'reviewKind'>
  location: Pick<Location, 'key' | 'pathname' | 'search' | 'state'>
  searchParams: URLSearchParams
  navigate: NavigateFunction
}

interface StudioArtifactContext {
  resultsProvenance: ResultsProvenance | null
  artifactPanelState: NovelShellArtifactPanelState | null
}

function applyStudioArtifactContextSearchParams(
  current: URLSearchParams,
  context: StudioArtifactContext,
): URLSearchParams {
  let next = setResultsProvenanceSearchParams(current, context.resultsProvenance)
  next = setNovelShellArtifactPanelSearchParams(next, context.artifactPanelState)
  return next
}

export function useStudioArtifactState({
  novelId,
  activeStage,
  activeChapterNum,
  routeState,
  location,
  searchParams,
  navigate,
}: UseStudioArtifactStateArgs) {
  const locationState = (location.state as StudioResultsLocationState | null) ?? null
  const [liveResultsDebugState, setLiveResultsDebugState] = useState<{
    key: string | null
    value: ContinueDebugSummary | null
  }>({
    key: null,
    value: null,
  })

  const [lastSummaryCategory, setLastSummaryCategory] = useState<InjectionSummaryCategory | null>(null)
  const artifactPanelState = useMemo(
    () => readNovelShellArtifactPanelSearchParams(searchParams),
    [searchParams],
  )
  const resultsProvenance = useMemo(
    () => readResultsProvenanceSearchParams(searchParams),
    [searchParams],
  )
  const canonicalResultsProvenance = useMemo(() => {
    const continuations = searchParams.get('continuations')?.trim()
    if (activeStage !== 'results' || activeChapterNum === null || !continuations) return null
    const totalVariantsRaw = searchParams.get('total_variants')
    const totalVariants = totalVariantsRaw ? Number(totalVariantsRaw) : null
    return {
      chapterNum: activeChapterNum,
      continuations,
      totalVariants: totalVariants !== null && Number.isFinite(totalVariants) ? totalVariants : null,
    }
  }, [activeChapterNum, activeStage, searchParams])

  const effectiveResultsProvenance = resultsProvenance ?? canonicalResultsProvenance
  const hasEphemeralResultsContext = (
    locationState?.streamParams != null
    && locationState?.novelId === novelId
  )
  const hasResultsContext = activeStage === 'results' || resultsProvenance !== null || hasEphemeralResultsContext
  const currentResultsDebugKey = useMemo(() => {
    if (effectiveResultsProvenance) return `persisted:${effectiveResultsProvenance.continuations}`
    if (hasEphemeralResultsContext) return `ephemeral:${location.key}`
    return null
  }, [effectiveResultsProvenance, hasEphemeralResultsContext, location.key])

  const liveResultsDebug = liveResultsDebugState.key === currentResultsDebugKey
    ? liveResultsDebugState.value
    : null
  const resultsDebug = useMemo(
    () => (
      !hasResultsContext
        ? null
        : liveResultsDebug
      ?? (effectiveResultsProvenance
        ? readGenerationResultsDebug(effectiveResultsProvenance.continuations) ?? locationState?.studioResultsDebug ?? null
        : locationState?.studioResultsDebug ?? null)
    ),
    [effectiveResultsProvenance, hasResultsContext, liveResultsDebug, locationState?.studioResultsDebug],
  )

  const injectionSummaryPanelState = useMemo(() => {
    if (!resultsDebug) return null
    return {
      panel: 'injection_summary' as const,
      injectionCategory: artifactPanelState.injectionCategory ?? lastSummaryCategory ?? pickInitialInjectionSummaryCategory(resultsDebug),
    }
  }, [artifactPanelState.injectionCategory, lastSummaryCategory, resultsDebug])
  const showInjectionSummaryRail = artifactPanelState.panel === 'injection_summary' && injectionSummaryPanelState !== null
  const activeArtifactPanelState = showInjectionSummaryRail ? injectionSummaryPanelState : null

  const resultsNavigationState = useMemo(() => {
    if (!hasResultsContext) return null
    return {
      ...(locationState ?? {}),
      studioResultsDebug: resultsDebug ?? null,
    }
  }, [hasResultsContext, locationState, resultsDebug])
  const atlasStudioOrigin = useMemo<AtlasStudioOriginState>(() => ({
    stage: activeStage,
    chapterNum: activeStage === 'results'
      ? (effectiveResultsProvenance?.chapterNum ?? activeChapterNum)
      : activeChapterNum,
    entityId: routeState.entityId,
    systemId: routeState.systemId,
    reviewKind: routeState.reviewKind,
    resultsProvenance: effectiveResultsProvenance,
    artifactPanelState: activeArtifactPanelState,
  }), [
    activeArtifactPanelState,
    activeChapterNum,
    activeStage,
    effectiveResultsProvenance,
    routeState.entityId,
    routeState.reviewKind,
    routeState.systemId,
  ])

  const applyActiveArtifactContextSearchParams = useCallback((current: URLSearchParams) => (
    applyStudioArtifactContextSearchParams(current, {
      resultsProvenance: effectiveResultsProvenance,
      artifactPanelState: activeArtifactPanelState,
    })
  ), [activeArtifactPanelState, effectiveResultsProvenance])

  const replaceArtifactPanelState = useCallback((nextState: NovelShellArtifactPanelState | null) => {
    const nextSearchParams = setNovelShellArtifactPanelSearchParams(new URLSearchParams(location.search), nextState)
    navigate(
      { pathname: location.pathname, search: nextSearchParams.toString() },
      { replace: true, state: resultsNavigationState },
    )
  }, [location.pathname, location.search, navigate, resultsNavigationState])

  const handleResultsDebugChange = useCallback((debug: ContinueDebugSummary | null) => {
    setLiveResultsDebugState({
      key: currentResultsDebugKey,
      value: debug,
    })
  }, [currentResultsDebugKey])

  const setInjectionSummaryCategory = useCallback((category: InjectionSummaryCategory) => {
    replaceArtifactPanelState({
      panel: 'injection_summary',
      injectionCategory: category,
    })
  }, [replaceArtifactPanelState])

  const toggleInjectionSummaryRail = useCallback(() => {
    if (!showInjectionSummaryRail && injectionSummaryPanelState === null) return
    if (showInjectionSummaryRail && injectionSummaryPanelState) setLastSummaryCategory(injectionSummaryPanelState.injectionCategory)
    replaceArtifactPanelState(showInjectionSummaryRail ? null : injectionSummaryPanelState)
  }, [injectionSummaryPanelState, replaceArtifactPanelState, showInjectionSummaryRail])

  const closeInjectionSummaryRail = useCallback(() => {
    if (injectionSummaryPanelState) setLastSummaryCategory(injectionSummaryPanelState.injectionCategory)
    replaceArtifactPanelState(null)
  }, [injectionSummaryPanelState, replaceArtifactPanelState])

  return {
    activeArtifactPanelState,
    applyActiveArtifactContextSearchParams,
    atlasStudioOrigin,
    currentResultsDebugKey,
    effectiveResultsProvenance,
    handleResultsDebugChange,
    hasResultsContext,
    injectionSummaryPanelState,
    locationState,
    resultsDebug,
    resultsNavigationState,
    setInjectionSummaryCategory,
    showInjectionSummaryRail,
    toggleInjectionSummaryRail,
    closeInjectionSummaryRail,
  }
}
