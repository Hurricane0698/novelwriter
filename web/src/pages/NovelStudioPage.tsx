// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense, useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PanelResizeHandle } from '@/components/novel-shell/PanelResizeHandle'
import { useElementWidth } from '@/hooks/useElementWidth'
import { StudioWorkspaceToolbar } from '@/components/studio/StudioWorkspaceToolbar'
import { StudioChapterToolbar } from '@/components/studio/StudioChapterToolbar'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { ChapterContent } from '@/components/detail/ChapterContent'
import { ChapterEditor } from '@/components/detail/ChapterEditor'
import { PageShell } from '@/components/layout/PageShell'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { useUpdateChapter } from '@/hooks/novel/useUpdateChapter'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import { useDeleteChapter } from '@/hooks/novel/useDeleteChapter'
import { useStudioOnboardingState } from '@/hooks/novel/useStudioOnboardingState'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { downloadTextFile } from '@/lib/downloadTextFile'
import {
  formatChapterBadgeLabel,
  formatChapterLabel,
  matchesChapterSearch,
} from '@/lib/chaptersPlainText'
import {
  getNativeNovelFileContract,
  serializeChapterToNativeFormat,
  serializeChaptersToNativeFormat,
} from '@/lib/chaptersNativeFormat'
import type { Novel } from '@/types/api'
import { useStudioChapterEditor } from '@/hooks/novel/useStudioChapterEditor'
import { useStudioNavigation } from '@/hooks/novel/useStudioNavigation'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useContinuationSetupState } from '@/hooks/novel/useContinuationSetupState'
import { useStudioArtifactState } from '@/hooks/novel/useStudioArtifactState'
import { getActiveWarnings, setActiveWarnings } from '@/lib/postcheckActiveWarningsStorage'
import { getWhitelist, addToWhitelist } from '@/lib/postcheckWhitelistStorage'
import { DriftWarningPopover } from '@/components/generation/DriftWarningPopover'
import { NovelShellLayout } from '@/components/novel-shell/NovelShellLayout'
import { ArtifactStage } from '@/components/novel-shell/ArtifactStage'
import { InjectionSummaryPanel } from '@/components/studio/panels/InjectionSummaryPanel'
import { StudioNavigationRail } from '@/components/studio/rail/StudioNavigationRail'
import { StudioSupportRail } from '@/components/studio/rail/StudioSupportRail'
import { StudioOnboardingStage } from '@/components/studio/stages/StudioOnboardingStage'
import { ContinuationSetupStage } from '@/components/studio/stages/ContinuationSetupStage'
import { StudioRelationshipStage } from '@/components/studio/stages/StudioRelationshipStage'
import { StudioSystemStage } from '@/components/studio/stages/StudioSystemStage'
import { ContinuationResultsStage } from '@/components/studio/stages/ContinuationResultsStage'
import { useNovelShell } from '@/components/novel-shell/NovelShellContext'
import {
  readWorldEntryHandoffSearchParams,
  readWorldEntryPendingSearchParams,
  setAtlasReviewKindSearchParams,
  setAtlasSuggestionTargetSearchParams,
  setAtlasTabSearchParams,
  setWorldEntryHandoffSearchParams,
  setWorldEntryPendingSearchParams,
} from '@/components/novel-shell/NovelShellRouteState'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { NovelCopilotDrawerFallback } from '@/components/novel-copilot/NovelCopilotDrawerFallback'
import {
  buildWholeBookCopilotLaunchArgs,
  buildCurrentEntityCopilotLaunchArgs,
  buildRelationshipResearchCopilotLaunchArgs,
} from '@/components/novel-copilot/novelCopilotLauncher'
import { useStudioCopilotTargetNavigation } from '@/components/novel-copilot/useCopilotTargetNavigation'
import type { TextAnnotation } from '@/components/ui/annotated-text'
import {
  resolveInjectionSummaryNavigationTarget,
  type InjectionSummaryCategory,
} from '@/lib/injectionSummaryNavigation'
import {
  getWindowIndexCopilotStatusMeta,
  getWindowIndexPollingInterval,
} from '@/lib/windowIndexStatus'
import {
  isWorldEntryPendingExpired,
  resolvePendingWorldEntryHandoffFromBootstrapJob,
} from '@/lib/worldEntryHandoff'
import { resolveStudioWorldEntryStage } from '@/lib/worldEntryLifecycle'
import type { CopilotReviewKind } from '@/types/copilot'
import {
  loadAtlasAssistWorkbench,
  scheduleAtlasAssistWorkbenchPrefetch,
} from '@/components/atlas/workbench/atlasAssistWorkbenchLoader'
import {
  loadNovelCopilotDrawer,
  scheduleNovelCopilotDrawerPrefetch,
} from '@/components/novel-copilot/novelCopilotDrawerLoader'

const NovelCopilotDrawer = lazy(async () => {
  const mod = await loadNovelCopilotDrawer()
  return { default: mod.NovelCopilotDrawer }
})
const StudioEntityStage = lazy(async () => {
  const mod = await import('@/components/studio/stages/StudioEntityStage')
  return { default: mod.StudioEntityStage }
})
const StudioDraftReviewStage = lazy(async () => {
  const mod = await import('@/components/studio/stages/StudioDraftReviewStage')
  return { default: mod.StudioDraftReviewStage }
})

function StudioStagePanelFallback() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="studio-stage-fallback">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-6 py-4">
        <div className="space-y-2">
          <div className="h-3 w-16 rounded bg-[hsl(var(--foreground)/0.10)]" />
          <div className="h-6 w-48 rounded bg-[hsl(var(--foreground)/0.12)]" />
          <div className="h-4 w-80 max-w-full rounded bg-[hsl(var(--foreground)/0.08)]" />
        </div>
      </div>
      <div className="flex-1 min-h-0 p-6">
        <div className="h-full rounded-[20px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
      </div>
    </div>
  )
}

function isUploadEntryLocationState(value: unknown): boolean {
  return (
    typeof value === 'object'
    && value !== null
    && (value as { novwrEntry?: unknown }).novwrEntry === 'upload'
  )
}

export function NovelStudioPage() {
  const { novelId: novelIdParam } = useParams<{ novelId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const novelId = Number(novelIdParam)
  const { locale, t } = useUiLocale()
  const { confirm: confirmDialog, dialogProps: confirmDialogProps } = useConfirmDialog()
  const { routeState, shellState } = useNovelShell()
  const { drawerWidth, setDrawerWidth } = shellState
  const { isOpen: isWorkbenchOpen, focusedSessionId, openDrawer, closeDrawer, reopenDrawer } = useNovelCopilot()
  const activeStage = routeState.stage ?? 'chapter'
  const showWorkbenchRail = isWorkbenchOpen && focusedSessionId !== null
  const worldEntryHandoff = useMemo(
    () => readWorldEntryHandoffSearchParams(searchParams),
    [searchParams],
  )
  const worldEntryPending = useMemo(
    () => readWorldEntryPendingSearchParams(searchParams),
    [searchParams],
  )
  const [suppressUploadEntryWorldOnboarding] = useState(
    () => isUploadEntryLocationState(location.state),
  )
  const warmAtlasAssist = useCallback(() => {
    void loadAtlasAssistWorkbench()
  }, [])

  useEffect(() => {
    if (!Number.isFinite(novelId)) return
    return scheduleAtlasAssistWorkbenchPrefetch()
  }, [novelId])

  useEffect(() => {
    if (!Number.isFinite(novelId)) return
    return scheduleNovelCopilotDrawerPrefetch()
  }, [novelId])

  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [chapterCreateError, setChapterCreateError] = useState<{
    novelId: number
    locationKey: string
    createGeneration: number
  } | null>(null)
  const [nativeExportError, setNativeExportError] = useState<{
    novelId: number
    locationKey: string
    exportGeneration: number
  } | null>(null)
  const [ingestRetryError, setIngestRetryError] = useState<{
    novelId: number
    locationKey: string
    retryGeneration: number
  } | null>(null)
  const [showMoreActions, setShowMoreActions] = useState(false)
  const [assistOpen, setAssistOpen] = useState<boolean | null>(null)
  const [chaptersOpen, setChaptersOpen] = useState(true)
  const [chapterRailWidth, setChapterRailWidth] = useState(256)
  const [continuationPanelWidth, setContinuationPanelWidth] = useState(320)
  const { ref: workspaceRef, width: workspaceWidth } = useElementWidth()
  const navigationOverlay = workspaceWidth < 760
  const visibleChapterWidth = Math.min(chapterRailWidth, Math.max(200, workspaceWidth - 48))
  const occupiedChapterWidth = chaptersOpen && !navigationOverlay ? visibleChapterWidth : 0
  const minimumStageWidth = activeStage === 'write' ? 640 : 420
  const maxAssistantWidth = Math.max(280, workspaceWidth - occupiedChapterWidth - minimumStageWidth)
  const assistantOverlay = workspaceWidth - occupiedChapterWidth < minimumStageWidth + 280
  const visibleDrawerWidth = Math.min(drawerWidth, assistantOverlay ? Math.max(280, workspaceWidth - 32) : maxAssistantWidth)

  const exportGenerationRef = useRef(0)
  const exportNovelContextRef = useRef({ novelId, locationKey: location.key })

  const ingestRetryGenerationRef = useRef(0)
  const ingestRetryNovelContextRef = useRef({ novelId, locationKey: location.key })

  const chapterCreateGenerationRef = useRef(0)
  const chapterCreateNovelContextRef = useRef({ novelId, locationKey: location.key })

  useLayoutEffect(() => {
    const nextContext = { novelId, locationKey: location.key }
    if (
      exportNovelContextRef.current.novelId !== nextContext.novelId
      || exportNovelContextRef.current.locationKey !== nextContext.locationKey
    ) {
      exportNovelContextRef.current = nextContext
      exportGenerationRef.current += 1
    }
    if (
      ingestRetryNovelContextRef.current.novelId !== nextContext.novelId
      || ingestRetryNovelContextRef.current.locationKey !== nextContext.locationKey
    ) {
      ingestRetryNovelContextRef.current = nextContext
      ingestRetryGenerationRef.current += 1
    }
    if (
      chapterCreateNovelContextRef.current.novelId !== nextContext.novelId
      || chapterCreateNovelContextRef.current.locationKey !== nextContext.locationKey
    ) {
      chapterCreateNovelContextRef.current = nextContext
      chapterCreateGenerationRef.current += 1
    }
  }, [location.key, novelId])

  useLayoutEffect(() => () => {
    exportGenerationRef.current += 1
    ingestRetryGenerationRef.current += 1
    chapterCreateGenerationRef.current += 1
  }, [])

  const { data: worldEntities = [], isLoading: worldEntitiesLoading } = useWorldEntities(novelId)
  const { data: worldSystems = [], isLoading: worldSystemsLoading } = useWorldSystems(novelId)
  const selectedStudioEntityStillExists = (
    routeState.entityId !== null && worldEntities.some((entity) => entity.id === routeState.entityId)
  )
  const effectiveStudioEntityId = routeState.entityId === null
    ? (worldEntities[0]?.id ?? null)
    : selectedStudioEntityStillExists ? routeState.entityId : (worldEntities[0]?.id ?? null)
  const effectiveStudioEntityName = effectiveStudioEntityId === null
    ? null
    : worldEntities.find((entity) => entity.id === effectiveStudioEntityId)?.name ?? null
  const selectedStudioSystemStillExists = (
    routeState.systemId !== null && worldSystems.some((system) => system.id === routeState.systemId)
  )
  const effectiveStudioSystemId = routeState.systemId === null
    ? (worldSystems[0]?.id ?? null)
    : selectedStudioSystemStillExists ? routeState.systemId : (worldSystems[0]?.id ?? null)
  const effectiveStudioSystemName = effectiveStudioSystemId === null
    ? null
    : worldSystems.find((system) => system.id === effectiveStudioSystemId)?.name ?? null

  const { data: novel, isLoading: novelLoading } = useQuery({
    queryKey: novelKeys.detail(novelId),
    queryFn: () => api.getNovel(novelId),
    enabled: !!novelIdParam,
    refetchInterval: (query) => getWindowIndexPollingInterval(query.state.data?.window_index, query.state.dataUpdateCount),
  })
  const cancelNovelDetailFetch = useCallback(async (targetNovelId: number) => {
    await queryClient.cancelQueries({
      queryKey: novelKeys.detail(targetNovelId),
      exact: true,
    })
  }, [queryClient])
  const fetchAuthoritativeNovelDetail = useCallback(async (targetNovelId: number) => {
    const queryKey = novelKeys.detail(targetNovelId)
    await cancelNovelDetailFetch(targetNovelId)
    await queryClient.invalidateQueries({ queryKey, exact: true, refetchType: 'none' })
    return queryClient.fetchQuery({
      queryKey,
      queryFn: () => api.getNovel(targetNovelId),
    })
  }, [cancelNovelDetailFetch, queryClient])
  const retryNovelIngest = useMutation({
    mutationFn: ({ targetNovelId }: {
      targetNovelId: number
      requestLocationKey: string
      retryGeneration: number
    }) => (
      api.retryNovelIngest(targetNovelId)
    ),
    onMutate: async ({ targetNovelId, requestLocationKey, retryGeneration }) => {
      await cancelNovelDetailFetch(targetNovelId)
      if (
        ingestRetryNovelContextRef.current.novelId === targetNovelId
        && ingestRetryNovelContextRef.current.locationKey === requestLocationKey
        && ingestRetryGenerationRef.current === retryGeneration
      ) {
        setIngestRetryError(null)
      }
    },
    onSuccess: async (updatedNovel, { targetNovelId, requestLocationKey, retryGeneration }) => {
      await cancelNovelDetailFetch(targetNovelId)
      queryClient.setQueryData(novelKeys.detail(targetNovelId), updatedNovel)
      if (
        ingestRetryNovelContextRef.current.novelId === targetNovelId
        && ingestRetryNovelContextRef.current.locationKey === requestLocationKey
        && ingestRetryGenerationRef.current === retryGeneration
      ) {
        setIngestRetryError(null)
      }
    },
    onError: async (_error, { targetNovelId, requestLocationKey, retryGeneration }) => {
      let refreshedNovel: Novel | null = null
      try {
        refreshedNovel = await fetchAuthoritativeNovelDetail(targetNovelId)
      } catch {
        // The original retry failure remains authoritative for visible feedback.
      }

      if (
        ingestRetryNovelContextRef.current.novelId !== targetNovelId
        || ingestRetryNovelContextRef.current.locationKey !== requestLocationKey
        || ingestRetryGenerationRef.current !== retryGeneration
      ) {
        return
      }
      const refreshedRetryStillFailed = (
        refreshedNovel?.window_index?.readiness === 'failed_retryable'
        && refreshedNovel.window_index.ingest?.status === 'failed'
      )
      if (refreshedNovel !== null && !refreshedRetryStillFailed) {
        setIngestRetryError(null)
        return
      }
      setIngestRetryError({
        novelId: targetNovelId,
        locationKey: requestLocationKey,
        retryGeneration,
      })
    },
  })
  const { data: bootstrapJob, isLoading: bootstrapLoading } = useBootstrapStatus(novelId, {
    refetchWhenMissing: novel?.window_index?.ingest?.bootstrap_plan != null,
  })
  const triggerBootstrap = useTriggerBootstrap(novelId)
  const chaptersMetaEnabled = (
    !!novelIdParam
    && (
      (novel?.window_index?.capabilities?.chapters_available ?? false)
      || (novel?.total_chapters ?? 0) > 0
    )
  )
  const { data: chaptersMeta = [] } = useQuery({
    queryKey: novelKeys.chaptersMeta(novelId),
    queryFn: () => api.listChaptersMeta(novelId),
    enabled: chaptersMetaEnabled,
    // Published chapters are immutable during deferred indexing; chapter edits
    // invalidate this cache through their mutations. Only poll active ingestion.
    refetchInterval: (query) => novel?.window_index?.ingest?.status === 'running'
      ? getWindowIndexPollingInterval(novel.window_index, query.state.dataUpdateCount) : false,
  })
  const activeChapterNum = useMemo(() => {
    if (
      routeState.chapterNum !== null
      && chaptersMeta.some((chapterMeta) => chapterMeta.chapter_number === routeState.chapterNum)
    ) {
      return routeState.chapterNum
    }
    return chaptersMeta[0]?.chapter_number ?? null
  }, [chaptersMeta, routeState.chapterNum])
  const chapterCreateErrorVisible = (
    chapterCreateError?.novelId === novelId
    && chapterCreateError.locationKey === location.key
  )
  const nativeExportErrorVisible = (
    nativeExportError?.novelId === novelId
    && nativeExportError.locationKey === location.key
  )
  const latestChapterNum = chaptersMeta.length > 0 ? chaptersMeta[chaptersMeta.length - 1].chapter_number : null
  const latestChapterMeta = chaptersMeta.length > 0 ? chaptersMeta[chaptersMeta.length - 1] : null
  const latestChapterReference = latestChapterMeta ? formatChapterBadgeLabel(latestChapterMeta) : null

  // Continuation setup state hoisted at page level so it survives stage mount/unmount.
  const continuationState = useContinuationSetupState(novelId, latestChapterNum)

  const updateChapter = useUpdateChapter(novelId, activeChapterNum ?? 0)
  const { mutate: createChapter, isPending: isCreatingChapter } = useCreateChapter(novelId)
  const deleteChapter = useDeleteChapter(novelId)
  const { data: chapter, isLoading: chapterLoading } = useQuery({
    queryKey: novelKeys.chapter(novelId, activeChapterNum ?? 0),
    queryFn: () => {
      if (activeChapterNum === null) {
        // Guard for type safety; `enabled` prevents this from running in practice.
        throw new Error('Missing active chapter number')
      }
      return api.getChapter(novelId, activeChapterNum)
    },
    enabled: !!novelIdParam && activeChapterNum !== null,
  })

  const {
    editMode, setEditMode, editorContent, editorSaveErrorCode, autoSaveStatus,
    handleEditorChange, handleSave, handleCancelEdit, saveCurrentEditorNow,
    resetEditor, toggleEdit,
  } = useStudioChapterEditor({
    novelId, chapterNumber: activeChapterNum, locationKey: location.key,
    chapterContent: chapter?.content ?? '', saveChapter: updateChapter.mutateAsync,
  })

  const currentMeta = useMemo(
    () => chaptersMeta.find(c => c.chapter_number === activeChapterNum),
    [activeChapterNum, chaptersMeta],
  )

  // ── Postcheck drift annotations (carried over from generation results) ──
  const [driftWhitelist, setDriftWhitelist] = useState<string[]>(() => getWhitelist(novelId))

  const handleDismissDriftTerm = useCallback((term: string) => {
    addToWhitelist(novelId, term)
    setDriftWhitelist(prev => [...prev, term])
  }, [novelId])

  // Active warnings for this chapter (used in both read and edit mode)
  const activeChapterWarnings = useMemo(() => {
    if (activeChapterNum === null) return []
    return getActiveWarnings(novelId, activeChapterNum, currentMeta?.created_at)
      .filter(w => !driftWhitelist.includes(w.term))
  }, [activeChapterNum, currentMeta?.created_at, driftWhitelist, novelId])

  // Read-mode: full annotations with popovers
  const chapterDriftAnnotations = useMemo<TextAnnotation[]>(() => {
    if (activeChapterWarnings.length === 0) return []
    return activeChapterWarnings.map(w => ({
      id: `drift-${w.code}-${w.term}`,
      term: w.term,
      className: 'nw-drift-highlight',
      renderPopover: ({ onClose }: { onClose: () => void }) => (
        <DriftWarningPopover
          code={w.code}
          term={w.term}
          onDismiss={() => {
            handleDismissDriftTerm(w.term)
            onClose()
          }}
        />
      ),
    }))
  }, [activeChapterWarnings, handleDismissDriftTerm])

  // Edit-mode: compact term list for the editor banner
  const editorWarningTerms = editMode && activeChapterWarnings.length > 0
    ? activeChapterWarnings.map(w => ({ code: w.code, term: w.term }))
    : undefined

  const chapterListItems = useMemo(() => {
    const filteredChapters = searchQuery.trim()
      ? chaptersMeta.filter((chapterMeta) => matchesChapterSearch(chapterMeta, searchQuery))
      : chaptersMeta
    return filteredChapters.map(chapter => ({
      chapterNumber: chapter.chapter_number,
      label: formatChapterLabel(chapter),
    }))
  }, [chaptersMeta, searchQuery])

  const handleExportAll = async () => {
    const exportingNovelId = novelId
    const exportingLocationKey = location.key
    const exportGeneration = exportGenerationRef.current + 1
    exportGenerationRef.current = exportGeneration
    setNativeExportError(null)
    const isCurrentExport = () => (
      exportGenerationRef.current === exportGeneration
      && exportNovelContextRef.current.novelId === exportingNovelId
      && exportNovelContextRef.current.locationKey === exportingLocationKey
    )
    try {
      const allChapters = await api.listChapters(exportingNovelId)
      if (!isCurrentExport()) return
      if (!novel) return
      const fileContract = getNativeNovelFileContract(novel.content_format)
      const content = serializeChaptersToNativeFormat(allChapters, novel.content_format)
      downloadTextFile(
        `${novel.title}_all_chapters_${new Date().toISOString().slice(0, 10)}${fileContract.extension}`,
        content,
        fileContract.mimeType,
      )
    } catch {
      if (isCurrentExport()) {
        setNativeExportError({
          novelId: exportingNovelId,
          locationKey: exportingLocationKey,
          exportGeneration,
        })
      }
    }
  }
  const handleExportChapter = () => {
    if (!novel || !chapter) return
    const exportGeneration = exportGenerationRef.current + 1
    exportGenerationRef.current = exportGeneration
    setNativeExportError(null)
    try {
      const fileContract = getNativeNovelFileContract(novel.content_format)
      downloadTextFile(
        `${novel.title}_${formatChapterBadgeLabel(chapter)}${fileContract.extension}`,
        serializeChapterToNativeFormat(chapter, novel.content_format),
        fileContract.mimeType,
      )
    } catch {
      setNativeExportError({ novelId, locationKey: location.key, exportGeneration })
    }
  }
  const handleTitleSave = () => {
    setEditingTitle(false)
    if (activeChapterNum === null || !currentMeta) return
    const newTitle = titleDraft.trim()
    if (newTitle === (currentMeta.title || '')) return
    updateChapter.mutate({ title: newTitle })
  }

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorInfo, setCursorInfo] = useState({ para: 1, col: 1 })
  const handleSelectionChange = () => {
    const ta = textareaRef.current; if (!ta) return
    const before = ta.value.slice(0, ta.selectionStart); const lines = before.split('\n')
    const para = lines.length
    const col = lines[lines.length - 1].length + 1
    setCursorInfo(current => current.para === para && current.col === col ? current : { para, col })
  }
  const handleUndo = () => { textareaRef.current?.focus(); document.execCommand('undo') }
  const handleRedo = () => { textareaRef.current?.focus(); document.execCommand('redo') }

  const windowIndexStatusMeta = getWindowIndexCopilotStatusMeta(novel?.window_index ?? null, locale)
  const artifactState = useStudioArtifactState({
    novelId,
    activeStage,
    activeChapterNum,
    routeState,
    location,
    searchParams,
    navigate,
  })
  const {
    handleResultsDebugChange, hasResultsContext, injectionSummaryPanelState,
    resultsDebug, setInjectionSummaryCategory, showInjectionSummaryRail,
    toggleInjectionSummaryRail, closeInjectionSummaryRail,
  } = artifactState

  const applyWorldEntryRouteSearchParams = useCallback((params: URLSearchParams) => {
    let next = setWorldEntryHandoffSearchParams(params, worldEntryHandoff)
    next = setWorldEntryPendingSearchParams(next, worldEntryPending)
    return next
  }, [worldEntryHandoff, worldEntryPending])

  const setStudioWorldEntryHandoff = useCallback((handoff: ReturnType<typeof readWorldEntryHandoffSearchParams>) => {
    setSearchParams((prev) => {
      let next = setWorldEntryHandoffSearchParams(prev, handoff)
      if (handoff) next = setWorldEntryPendingSearchParams(next, null)
      return next
    }, { replace: true })
  }, [setSearchParams])

  const setStudioWorldEntryPending = useCallback((pending: ReturnType<typeof readWorldEntryPendingSearchParams>) => {
    setSearchParams((prev) => {
      let next = setWorldEntryPendingSearchParams(prev, pending)
      if (pending) next = setWorldEntryHandoffSearchParams(next, null)
      return next
    }, { replace: true })
  }, [setSearchParams])

  useEffect(() => {
    const nextHandoff = resolvePendingWorldEntryHandoffFromBootstrapJob(worldEntryPending, bootstrapJob)
    if (nextHandoff) {
      setSearchParams((prev) => {
        let next = setWorldEntryHandoffSearchParams(prev, nextHandoff)
        next = setWorldEntryPendingSearchParams(next, null)
        return next
      }, { replace: true })
      return
    }

    if (!isWorldEntryPendingExpired(worldEntryPending)) return

    setSearchParams((prev) => setWorldEntryPendingSearchParams(prev, null), { replace: true })
  }, [bootstrapJob, setSearchParams, worldEntryPending])

  const {
    navigateToChapterStage, navigateToResultsStage, navigateToWriteStage,
    navigateToEntityStage, navigateToReviewStage, navigateToRelationshipStage,
    navigateToSystemStage, navigateToAtlas,
  } = useStudioNavigation({
    novelId, activeChapterNum, artifacts: artifactState,
    editor: { editMode, setEditMode, saveCurrentEditorNow },
    applyWorldEntryRouteSearchParams, warmAtlasAssist,
  })
  const handleSelectChapter = useCallback((chapterNumber: number) => {
    resetEditor()
    setEditingTitle(false)
    setShowMoreActions(false)
    navigateToChapterStage(chapterNumber)
  }, [navigateToChapterStage, resetEditor])
  const handleCreateChapter = useCallback(() => {
    const targetNovelId = novelId
    const targetLocationKey = location.key
    const createGeneration = chapterCreateGenerationRef.current + 1
    chapterCreateGenerationRef.current = createGeneration
    setChapterCreateError(null)
    createChapter({ title: '', content: '' }, {
      onSuccess: (nc) => {
        if (
          chapterCreateNovelContextRef.current.novelId !== targetNovelId
          || chapterCreateNovelContextRef.current.locationKey !== targetLocationKey
          || chapterCreateGenerationRef.current !== createGeneration
        ) {
          return
        }
        resetEditor('', true)
        setEditingTitle(false)
        setShowMoreActions(false)
        navigateToChapterStage(nc.chapter_number)
      },
      onError: () => {
        if (
          chapterCreateNovelContextRef.current.novelId === targetNovelId
          && chapterCreateNovelContextRef.current.locationKey === targetLocationKey
          && chapterCreateGenerationRef.current === createGeneration
        ) {
          setChapterCreateError({
            novelId: targetNovelId,
            locationKey: targetLocationKey,
            createGeneration,
          })
        }
      },
    })
  }, [createChapter, location.key, navigateToChapterStage, novelId, resetEditor])
  const handleDeleteChapter = async () => {
    if (activeChapterNum === null) return
    const confirmed = await confirmDialog({
      title: t('studio.chapter.delete'),
      description: t('studio.chapter.deleteConfirm', { chapter: activeChapterReference ?? `Ch. ${activeChapterNum}` }),
      confirmText: t('studio.chapter.delete'),
      tone: 'destructive',
    })
    if (!confirmed) return
    deleteChapter.mutate(activeChapterNum, {
      onSuccess: () => {
        resetEditor()
        // Clean up persisted drift warnings for the deleted chapter
        setActiveWarnings(novelId, activeChapterNum, [])
        const idx = chaptersMeta.findIndex(c => c.chapter_number === activeChapterNum)
        const next = chaptersMeta[idx + 1] ?? chaptersMeta[idx - 1]
        setEditingTitle(false)
        setShowMoreActions(false)
        navigateToChapterStage(next?.chapter_number ?? null)
      },
    })
  }
  const handleReturnToArtifact = () => {
    if (hasResultsContext) {
      navigateToResultsStage()
      return
    }
    navigateToChapterStage(activeChapterNum)
  }
  const handleStudioLocateTarget = useStudioCopilotTargetNavigation({
    navigateToReviewStage,
    navigateToEntityStage: (entityId) => navigateToEntityStage(entityId),
    navigateToRelationshipStage: (entityId) => navigateToRelationshipStage(entityId),
    navigateToSystemStage: (systemId) => navigateToSystemStage(systemId),
    navigateToAtlas,
  })
  const handleOpenInjectionCategory = useCallback((tab: InjectionSummaryCategory) => {
    navigateToAtlas(setAtlasTabSearchParams(new URLSearchParams(), tab))
  }, [navigateToAtlas])
  const handleOpenInjectionItem = useCallback((category: InjectionSummaryCategory, label: string) => {
    const target = resolveInjectionSummaryNavigationTarget({
      category,
      label,
      entities: worldEntities,
      systems: worldSystems,
    })

    if (target.kind === 'studio_entity') {
      navigateToEntityStage(target.entityId, { replace: true })
      return
    }

    if (target.kind === 'studio_relationship') {
      navigateToRelationshipStage(target.entityId, { replace: true })
      return
    }

    if (target.kind === 'studio_system') {
      navigateToSystemStage(target.systemId, { replace: true })
      return
    }

    navigateToAtlas(setAtlasTabSearchParams(new URLSearchParams(), target.tab))
  }, [navigateToAtlas, navigateToEntityStage, navigateToRelationshipStage, navigateToSystemStage, worldEntities, worldSystems])
  const openEntityCopilot = useCallback(() => {
    if (effectiveStudioEntityId === null) return
    openDrawer(...buildCurrentEntityCopilotLaunchArgs({
      entityId: effectiveStudioEntityId,
      entityName: effectiveStudioEntityName,
      surface: 'studio',
      stage: 'entity',
    }))
  }, [effectiveStudioEntityId, effectiveStudioEntityName, openDrawer])
  const openRelationshipCopilot = useCallback(() => {
    if (effectiveStudioEntityId === null) return
    openDrawer(...buildRelationshipResearchCopilotLaunchArgs({
      entityId: effectiveStudioEntityId,
      entityName: effectiveStudioEntityName,
      surface: 'studio',
      stage: 'relationship',
    }))
  }, [effectiveStudioEntityId, effectiveStudioEntityName, openDrawer])
  const contextualCopilotAction = useMemo(() => {
    if (activeStage === 'entity' && effectiveStudioEntityId !== null) {
      return {
        title: t('studio.contextualCopilot.entity.title'),
        description: effectiveStudioEntityName
          ? t('studio.contextualCopilot.entity.description', { subject: effectiveStudioEntityName })
          : t('studio.contextualCopilot.entity.descriptionFallback'),
        onClick: openEntityCopilot,
      }
    }
    if (activeStage === 'relationship' && effectiveStudioEntityId !== null) {
      return {
        title: t('studio.contextualCopilot.relationship.title'),
        description: effectiveStudioEntityName
          ? t('studio.contextualCopilot.relationship.description', { subject: effectiveStudioEntityName })
          : t('studio.contextualCopilot.relationship.descriptionFallback'),
        onClick: openRelationshipCopilot,
      }
    }
    return undefined
  }, [activeStage, effectiveStudioEntityId, effectiveStudioEntityName, openEntityCopilot, openRelationshipCopilot, t])
  const worldLoading = worldEntitiesLoading || worldSystemsLoading || bootstrapLoading
  const handleRetryNovelIngest = () => {
    const retryGeneration = ingestRetryGenerationRef.current + 1
    ingestRetryGenerationRef.current = retryGeneration
    setIngestRetryError(null)
    retryNovelIngest.mutate({
      targetNovelId: novelId,
      requestLocationKey: location.key,
      retryGeneration,
    })
  }
  const {
    bootstrapError,
    chaptersAvailable,
    handleDismissWorldOnboarding,
    handleTriggerBootstrap,
    preparationGate,
    showWorldOnboarding,
    worldGenOpen,
    setWorldGenOpen,
  } = useStudioOnboardingState({
    novelId,
    novel,
    locale,
    t,
    worldEntityCount: worldEntities.length,
    worldSystemCount: worldSystems.length,
    worldLoading,
    bootstrapLoading,
    bootstrapJob,
    bootstrapTriggerPending: triggerBootstrap.isPending,
    suppressWorldOnboarding: suppressUploadEntryWorldOnboarding,
    triggerInitialBootstrap: (handlers) => {
      triggerBootstrap.mutate(
        { mode: 'initial' },
        {
          onError: (error) => {
            handlers?.onError?.(error)
          },
        },
      )
    },
    retryIngest: handleRetryNovelIngest,
    returnToLibrary: () => navigate('/library'),
    dismissWorldOnboardingRoute: () => {
      navigate(`/world/${novelId}`)
    },
  })
  const visiblePreparationGate = (
    preparationGate
    && ingestRetryError?.novelId === novelId
    && ingestRetryError.locationKey === location.key
  )
    ? {
        ...preparationGate,
        error: t('studio.preparation.retryFailed'),
      }
    : preparationGate

  const assistNeedsAttention = resolveStudioWorldEntryStage({
    worldEntityCount: worldEntities.length,
    worldSystemCount: worldSystems.length,
    handoff: worldEntryHandoff,
    pending: worldEntryPending,
  }) !== 'routine'
  const showAssistRail = assistOpen ?? assistNeedsAttention
  const closeAssistant = () => { closeDrawer(); setAssistOpen(false) }
  const handleToggleAssist = () => {
    if (showWorkbenchRail || showAssistRail) closeAssistant()
    else if (focusedSessionId) reopenDrawer()
    else setAssistOpen(true)
  }
  const handleToggleWriting = () => {
    if (activeStage === 'write') { navigateToChapterStage(activeChapterNum); return }
    if (editMode) {
      void saveCurrentEditorNow().then(isCurrentSave => {
        if (!isCurrentSave) return
        setEditMode(false)
        navigateToWriteStage()
      }).catch(() => { /* Keep the editor open when saving fails. */ })
    } else navigateToWriteStage()
  }

  if (novelLoading) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-muted-foreground">{t('studio.loading')}</span>
      </PageShell>
    )
  }
  if (!novel) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-[hsl(var(--color-warning))]">{t('studio.novelNotFound')}</span>
      </PageShell>
    )
  }

  const currentChapterIdentity = chapter ?? currentMeta ?? null
  const activeChapterReference = currentChapterIdentity ? formatChapterBadgeLabel(currentChapterIdentity) : null
  const showEntryStage = visiblePreparationGate !== null || showWorldOnboarding

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="min-h-0 flex-1 overflow-hidden">
      {showEntryStage ? (
        <StudioOnboardingStage
          preparationGate={visiblePreparationGate}
          showWorldOnboarding={showWorldOnboarding}
          bootstrapPending={triggerBootstrap.isPending}
          preparationActionPending={
            triggerBootstrap.isPending
            || (
              retryNovelIngest.isPending
              && retryNovelIngest.variables?.targetNovelId === novelId
            )
          }
          bootstrapError={bootstrapError}
          chaptersAvailable={chaptersAvailable}
          onWorldGenOpenChange={setWorldGenOpen}
          onTriggerBootstrap={handleTriggerBootstrap}
          onDismissWorldOnboarding={handleDismissWorldOnboarding}
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          {chapterCreateErrorVisible ? (
            <div
              role="alert"
              data-testid="chapter-create-error"
              className="shrink-0 rounded-[12px] border border-[hsl(var(--color-danger)/0.25)] bg-[hsl(var(--color-danger)/0.08)] px-4 py-2 text-sm text-[hsl(var(--color-danger))]"
            >
              {t('studio.chapter.createFailed')}
            </div>
          ) : null}
          {nativeExportErrorVisible ? (
            <div
              role="alert"
              data-testid="native-export-error"
              className="shrink-0 rounded-[12px] border border-[hsl(var(--color-danger)/0.25)] bg-[hsl(var(--color-danger)/0.08)] px-4 py-2 text-sm text-[hsl(var(--color-danger))]"
            >
              {t('studio.actions.exportFailed')}
            </div>
          ) : null}
          <StudioWorkspaceToolbar title={novel.title} chaptersOpen={chaptersOpen}
            onToggleChapters={() => setChaptersOpen(current => !current)} writing={activeStage === 'write'}
            onToggleWriting={handleToggleWriting} canContinue={latestChapterNum !== null}
            assistantOpen={showWorkbenchRail || showAssistRail} onToggleAssistant={handleToggleAssist}
            onOpenAtlas={() => { setShowMoreActions(false); navigateToAtlas() }} onWarmAtlas={warmAtlasAssist} />
          <div ref={workspaceRef} className="relative flex min-h-0 flex-1 overflow-hidden">
          {((navigationOverlay && chaptersOpen) || (assistantOverlay && (showWorkbenchRail || showAssistRail))) && (
            <div aria-hidden="true" className="absolute inset-0 z-20 bg-background/80" onClick={() => {
              if (navigationOverlay) setChaptersOpen(false)
              if (assistantOverlay) closeAssistant()
            }} />
          )}
          <NovelShellLayout className="flex-1 min-h-0 overflow-hidden bg-background">
            <aside id="studio-chapters" hidden={!chaptersOpen} data-testid="studio-chapter-panel"
              className={`relative shrink-0 border-r border-border/50 bg-background ${chaptersOpen ? 'flex flex-col' : 'hidden'} ${navigationOverlay ? '!absolute inset-y-0 left-0 z-30 shadow-xl' : ''}`}
              style={{ width: visibleChapterWidth }}>
              <PanelResizeHandle side="right" width={visibleChapterWidth} min={200} max={Math.min(400, Math.max(200, workspaceWidth - 48))}
                onResize={setChapterRailWidth} label={t('studio.layout.resizeChapters')} />
              <StudioNavigationRail
                novelTitle={novel.title}
                searchQuery={searchQuery}
                onSearchQueryChange={setSearchQuery}
                chapters={chapterListItems}
                selectedChapterNumber={activeChapterNum}
                onSelectChapter={chapterNumber => { handleSelectChapter(chapterNumber); if (navigationOverlay) setChaptersOpen(false) }}
                chapterCount={chaptersMeta.length}
                onCreateChapter={handleCreateChapter}
                isCreating={isCreatingChapter}
                onClose={() => setChaptersOpen(false)}
                activeStage={activeStage}
              />
            </aside>

          {/* ── Content Area ── */}
          <ArtifactStage variant="glass">
            {hasResultsContext ? (
              <div className={activeStage === 'results' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
              <ContinuationResultsStage
                novelId={novelId}
                contentFormat={novel.content_format}
                isActive={activeStage === 'results'}
                activeChapterNum={activeChapterNum}
                activeChapterReference={activeChapterReference}
                showInjectionSummaryRail={showInjectionSummaryRail}
                onToggleInjectionSummaryRail={toggleInjectionSummaryRail}
                  onDebugChange={handleResultsDebugChange}
                  assistOpen={showAssistRail}
                />
              </div>
            ) : null}

            {activeStage === 'results' ? null : activeStage === 'write' && latestChapterNum !== null ? (
              /* ── Write Stage ── */
              <ContinuationSetupStage
                novelId={novelId}
                contentFormat={novel.content_format}
                panelWidth={continuationPanelWidth}
                onPanelResize={setContinuationPanelWidth}
                onClose={() => navigateToChapterStage(activeChapterNum)}
                chapterNum={latestChapterNum}
                chapterReference={latestChapterReference}
                instruction={continuationState.instruction}
                onInstructionChange={continuationState.setInstruction}
                selectedLength={continuationState.selectedLength}
                onSelectedLengthChange={continuationState.setSelectedLength}
                advancedOpen={continuationState.advancedOpen}
                onAdvancedOpenChange={continuationState.setAdvancedOpen}
                contextChapters={continuationState.contextChapters}
                onContextChaptersChange={continuationState.setContextChapters}
                numVersions={continuationState.numVersions}
                onNumVersionsChange={continuationState.setNumVersions}
                temperature={continuationState.temperature}
                onTemperatureChange={continuationState.setTemperature}
                contextSummaries={continuationState.contextSummaries}
                contextSummariesLoading={continuationState.contextSummariesLoading}
                contextSummaryError={continuationState.contextSummaryError}
                selectedContextSummaryIds={continuationState.selectedContextSummaryIds}
                onSelectedContextSummaryIdsChange={continuationState.setSelectedContextSummaryIds}
                contextSummaryRange={continuationState.contextSummaryRange}
                onContextSummaryRangeChange={continuationState.setContextSummaryRange}
                contextSummaryGenerating={continuationState.contextSummaryGenerating}
                contextSummaryDeletingId={continuationState.contextSummaryDeletingId}
                contextSummarySaving={continuationState.contextSummarySaving}
                contextSummaryRegenerating={continuationState.contextSummaryRegenerating}
                reviewContextSummary={continuationState.reviewContextSummary}
                onReviewContextSummaryChange={continuationState.setReviewContextSummaryId}
                onCreateContextSummary={continuationState.handleCreateContextSummary}
                onSaveContextSummary={continuationState.handleSaveContextSummary}
                onRegenerateContextSummary={continuationState.handleRegenerateContextSummary}
                onDeleteContextSummary={continuationState.handleDeleteContextSummary}
                onGenerate={continuationState.handleGenerate}
                assistOpen={showAssistRail}
              />
            ) : activeStage === 'entity' ? (
              <Suspense fallback={<StudioStagePanelFallback />}>
                <StudioEntityStage
                  novelId={novelId}
                  entityId={effectiveStudioEntityId}
                  onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                  onOpenCopilot={openEntityCopilot}
                  onOpenAtlas={() => {
                    const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                      resource: 'entity',
                      resource_id: effectiveStudioEntityId,
                      label: 'entity',
                      tab: 'entities',
                    })
                    navigateToAtlas(nextParams)
                  }}
                  onWarmAtlas={warmAtlasAssist}
                  assistOpen={showAssistRail}
                />
              </Suspense>
            ) : activeStage === 'relationship' ? (
              <StudioRelationshipStage
                novelId={novelId}
                entityId={effectiveStudioEntityId}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                onOpenCopilot={openRelationshipCopilot}
                onOpenAtlas={() => {
                  const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                    resource: 'relationship',
                    resource_id: effectiveStudioEntityId,
                    label: 'relationship',
                    tab: 'relationships',
                    entity_id: effectiveStudioEntityId,
                  })
                  navigateToAtlas(nextParams)
                }}
                onWarmAtlas={warmAtlasAssist}
                assistOpen={showAssistRail}
              />
            ) : activeStage === 'review' ? (
              <Suspense fallback={<StudioStagePanelFallback />}>
                <StudioDraftReviewStage
                  novelId={novelId}
                  reviewKind={routeState.reviewKind ?? 'entities'}
                  onReviewKindChange={(kind) => navigateToReviewStage(kind, { replace: true })}
                  onOpenEntity={(entityId) => navigateToEntityStage(entityId, { replace: true })}
                  onOpenRelationships={(entityId) => navigateToRelationshipStage(entityId, { replace: true })}
                  onOpenSystem={(systemId) => navigateToSystemStage(systemId, { replace: true })}
                  onOpenAtlas={() => {
                    const nextParams = setAtlasReviewKindSearchParams(new URLSearchParams(), routeState.reviewKind ?? 'entities')
                    navigateToAtlas(nextParams)
                  }}
                  onWarmAtlas={warmAtlasAssist}
                  onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                  assistOpen={showAssistRail}
                />
              </Suspense>
            ) : activeStage === 'system' ? (
              <StudioSystemStage
                novelId={novelId}
                systemId={effectiveStudioSystemId}
                onSelectSystem={(systemId) => navigateToSystemStage(systemId, { replace: true })}
                onOpenAtlas={() => {
                  const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                    resource: 'system',
                    resource_id: effectiveStudioSystemId,
                    label: effectiveStudioSystemName ?? 'system',
                    tab: 'systems',
                  })
                  navigateToAtlas(nextParams)
                }}
                onWarmAtlas={warmAtlasAssist}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                assistOpen={showAssistRail}
              />
            ) : (
              /* ── Chapter Stage ── */
              <div className="flex-1 min-h-0 min-w-0 flex flex-col gap-4 px-5 py-5 sm:px-8 overflow-hidden">
                <StudioChapterToolbar
                  currentMeta={currentMeta}
                  currentChapterIdentity={currentChapterIdentity}
                  updatedAt={chapter?.updated_at ?? chapter?.created_at ?? currentMeta?.created_at}
                  content={editMode ? editorContent : (chapter?.content ?? '')}
                  canEdit={activeChapterNum !== null}
                  canDelete={activeChapterNum !== null && chaptersMeta.length > 1}
                  editor={{ editMode, editingTitle, titleDraft, setTitleDraft, setEditingTitle, handleTitleSave, toggleEdit }}
                  actions={{
                    isOpen: showMoreActions, onOpenChange: setShowMoreActions,
                    exportChapter: handleExportChapter, exportAll: handleExportAll, deleteChapter: handleDeleteChapter,
                  }}
                  assistOpen={showAssistRail}
                />

                {/* ── Editor / Reader Area ── */}
                {editMode && activeChapterNum !== null ? (
                    <ChapterEditor
                      textareaRef={textareaRef}
                      value={editorContent}
                      onChange={handleEditorChange}
                      onSelectionChange={handleSelectionChange}
                      cursorInfo={cursorInfo}
                      autoSaveStatus={autoSaveStatus}
                      saveErrorCode={editorSaveErrorCode}
                      onUndo={handleUndo}
                      onRedo={handleRedo}
                      onCancel={handleCancelEdit}
                      onSave={handleSave}
                      warningTerms={editorWarningTerms}
                      previewAnnotations={chapterDriftAnnotations}
                      contentFormat={novel.content_format}
                  />
                ) : (
                  <ChapterContent
                    isLoading={chapterLoading}
                    content={chapter?.content ?? null}
                    contentFormat={novel.content_format}
                    annotations={chapterDriftAnnotations}
                  />
                )}
              </div>
            )}
          </ArtifactStage>

          {showWorkbenchRail ? (
            <Suspense fallback={<NovelCopilotDrawerFallback width={visibleDrawerWidth} />}>
              <NovelCopilotDrawer novelId={novelId} width={visibleDrawerWidth}
                presentation={assistantOverlay ? 'overlay' : 'rail'} onClose={closeAssistant}
                onBack={() => { closeDrawer(); setAssistOpen(true) }}
                onLocateTarget={handleStudioLocateTarget} />
            </Suspense>
          ) : (showInjectionSummaryRail && resultsDebug) || showAssistRail ? (
            <aside className={`relative shrink-0 border-l border-border/50 bg-background ${assistantOverlay ? '!absolute inset-y-0 right-0 z-30 shadow-xl' : ''}`}
              style={{ width: visibleDrawerWidth }} data-testid="studio-support-panel">
              <PanelResizeHandle side="left" width={visibleDrawerWidth} min={280}
                max={assistantOverlay ? Math.max(280, workspaceWidth - 32) : maxAssistantWidth}
                onResize={setDrawerWidth} label={t('copilot.drawer.resize')} />
              {showInjectionSummaryRail && resultsDebug ? (
                <InjectionSummaryPanel debug={resultsDebug} activeCategory={injectionSummaryPanelState?.injectionCategory ?? undefined}
                  onActiveCategoryChange={setInjectionSummaryCategory} onClose={closeInjectionSummaryRail}
                  onOpenAtlas={handleOpenInjectionCategory} onWarmAtlas={warmAtlasAssist} onSelectItem={handleOpenInjectionItem} />
              ) : (
            <StudioSupportRail
              onClose={closeAssistant}
              novelId={novelId}
              worldEntityCount={worldEntities.length}
              worldSystemCount={worldSystems.length}
              windowIndexStatus={windowIndexStatusMeta}
              onOpenWholeBookCopilot={() => {
                openDrawer(...buildWholeBookCopilotLaunchArgs(routeState))
              }}
              worldEntryHandoff={worldEntryHandoff}
              worldEntryPending={worldEntryPending}
              onWorldEntryHandoffChange={setStudioWorldEntryHandoff}
              onWorldEntryPendingChange={setStudioWorldEntryPending}
              onOpenAtlas={() => {
                setShowMoreActions(false)
                navigateToAtlas()
              }}
              onOpenAtlasReview={(reviewKind: CopilotReviewKind) => {
                setShowMoreActions(false)
                const nextParams = setAtlasReviewKindSearchParams(new URLSearchParams(), reviewKind)
                navigateToAtlas(nextParams)
              }}
              onWarmAtlas={warmAtlasAssist}
              contextualCopilotAction={contextualCopilotAction}
            />
              )}
            </aside>
          ) : null}
          </NovelShellLayout>
          </div>
        </div>
      )}
      {/* Keep the mutation observer mounted when generated entities hide onboarding. */}
      <WorldGenerationDialog
        novelId={novelId}
        open={worldGenOpen}
        onOpenChange={setWorldGenOpen}
        analyticsSource="world_onboarding"
      />
      <ConfirmDialog {...confirmDialogProps} />
    </PageShell>
  )
}
