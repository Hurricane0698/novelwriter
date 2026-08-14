// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense, useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, Pencil, Trash2, Upload } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { ChapterContent } from '@/components/detail/ChapterContent'
import {
  ChapterEditor,
  type ChapterEditorSaveErrorCode,
} from '@/components/detail/ChapterEditor'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { GlassSurface } from '@/components/ui/glass-surface'
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
import { formatRelativeTime } from '@/lib/formatRelativeTime'
import { downloadTextFile } from '@/lib/downloadTextFile'
import {
  formatChapterBadgeLabel,
  formatChapterLabel,
  getChapterDisplayTitle,
  matchesChapterSearch,
} from '@/lib/chaptersPlainText'
import {
  getNativeNovelFileContract,
  serializeChapterToNativeFormat,
  serializeChaptersToNativeFormat,
} from '@/lib/chaptersNativeFormat'
import { isMarkdownChapterBodyInvalidError } from '@/lib/chapterMutationError'
import type { Novel } from '@/types/api'
import { useDebouncedAutoSave } from '@/hooks/useDebouncedAutoSave'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useContinuationSetupState } from '@/hooks/novel/useContinuationSetupState'
import { useStudioArtifactState } from '@/hooks/novel/useStudioArtifactState'
import { getActiveWarnings, setActiveWarnings } from '@/lib/postcheckActiveWarningsStorage'
import { getWhitelist, addToWhitelist } from '@/lib/postcheckWhitelistStorage'
import { DriftWarningPopover } from '@/components/generation/DriftWarningPopover'
import { NovelShellLayout } from '@/components/novel-shell/NovelShellLayout'
import { NovelShellRail } from '@/components/novel-shell/NovelShellRail'
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
  setAtlasStudioOriginSearchParams,
  setNovelShellArtifactPanelSearchParams,
  setAtlasReviewKindSearchParams,
  setResultsProvenanceSearchParams,
  setAtlasSuggestionTargetSearchParams,
  setAtlasTabSearchParams,
  setWorldEntryHandoffSearchParams,
  setWorldEntryPendingSearchParams,
  setStudioChapterSearchParams,
  setStudioEntityStageSearchParams,
  setStudioRelationshipStageSearchParams,
  setStudioResultsStageSearchParams,
  setStudioSystemStageSearchParams,
  setStudioReviewKindSearchParams,
  setStudioStageSearchParams,
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

function countWords(text: string): number {
  return text.replace(/\s/g, '').length
}

const AUTO_SAVE_DELAY = 3000
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
  const { drawerWidth } = shellState
  const { isOpen: isWorkbenchOpen, focusedSessionId, openDrawer } = useNovelCopilot()
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

  const [editMode, setEditMode] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [editorContent, setEditorContent] = useState('')
  const [editorSaveError, setEditorSaveError] = useState<{
    novelId: number
    chapterNumber: number
    locationKey: string
    saveGeneration: number
    code: ChapterEditorSaveErrorCode
  } | null>(null)
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
  const [assistOpen, setAssistOpen] = useState(true)

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
    refetchInterval: (query) => getWindowIndexPollingInterval(query.state.data?.window_index ?? null),
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
  const chaptersMetaPollingInterval = getWindowIndexPollingInterval(novel?.window_index ?? null)
  const { data: chaptersMeta = [] } = useQuery({
    queryKey: novelKeys.chaptersMeta(novelId),
    queryFn: () => api.listChaptersMeta(novelId),
    enabled: chaptersMetaEnabled,
    refetchInterval: chaptersMetaPollingInterval,
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
  const editorSaveGenerationRef = useRef(0)
  const editorSaveContextRef = useRef({
    novelId,
    chapterNumber: activeChapterNum,
    locationKey: location.key,
  })
  useLayoutEffect(() => {
    const nextContext = {
      novelId,
      chapterNumber: activeChapterNum,
      locationKey: location.key,
    }
    if (
      editorSaveContextRef.current.novelId !== nextContext.novelId
      || editorSaveContextRef.current.chapterNumber !== nextContext.chapterNumber
      || editorSaveContextRef.current.locationKey !== nextContext.locationKey
    ) {
      editorSaveContextRef.current = nextContext
      editorSaveGenerationRef.current += 1
    }
  }, [activeChapterNum, location.key, novelId])
  const editorSaveErrorCode = (
    editorSaveError?.novelId === novelId
    && editorSaveError.chapterNumber === activeChapterNum
    && editorSaveError.locationKey === location.key
  )
    ? editorSaveError.code
    : null
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
  const createChapter = useCreateChapter(novelId)
  const deleteChapter = useDeleteChapter(novelId)
  const {
    status: autoSaveStatus,
    schedule: scheduleAutoSave,
    saveNow: saveNowAutoSave,
    cancel: cancelAutoSave,
  } = useDebouncedAutoSave<string>({
    delayMs: AUTO_SAVE_DELAY,
    save: async (content) => {
      const savingNovelId = novelId
      const savingChapterNumber = activeChapterNum
      const savingLocationKey = location.key
      if (savingChapterNumber === null) return
      const saveGeneration = editorSaveGenerationRef.current + 1
      editorSaveGenerationRef.current = saveGeneration
      setEditorSaveError(null)
      const isCurrentSave = () => (
        editorSaveGenerationRef.current === saveGeneration
        && editorSaveContextRef.current.novelId === savingNovelId
        && editorSaveContextRef.current.chapterNumber === savingChapterNumber
        && editorSaveContextRef.current.locationKey === savingLocationKey
      )
      try {
        await updateChapter.mutateAsync({ content })
        if (isCurrentSave()) {
          setEditorSaveError(null)
        }
      } catch (error) {
        if (isCurrentSave()) {
          setEditorSaveError({
            novelId: savingNovelId,
            chapterNumber: savingChapterNumber,
            locationKey: savingLocationKey,
            saveGeneration,
            code: isMarkdownChapterBodyInvalidError(error) ? error.code : 'chapter_save_failed',
          })
        }
        throw error
      }
    },
  })
  const saveCurrentEditorNow = useCallback(async (): Promise<boolean> => {
    const targetNovelId = novelId
    const targetChapterNumber = activeChapterNum
    const targetLocationKey = location.key
    if (targetChapterNumber === null) return false
    const savePromise = saveNowAutoSave(editorContent)
    // useDebouncedAutoSave invokes the current save callback synchronously before
    // yielding, so this is the generation reserved for this manual save.
    const saveGeneration = editorSaveGenerationRef.current
    await savePromise
    return (
      editorSaveGenerationRef.current === saveGeneration
      && editorSaveContextRef.current.novelId === targetNovelId
      && editorSaveContextRef.current.chapterNumber === targetChapterNumber
      && editorSaveContextRef.current.locationKey === targetLocationKey
    )
  }, [activeChapterNum, editorContent, location.key, novelId, saveNowAutoSave])

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

  const currentMeta = chaptersMeta.find(c => c.chapter_number === activeChapterNum)

  // ── Postcheck drift annotations (carried over from generation results) ──
  const [driftWhitelist, setDriftWhitelist] = useState<string[]>(() => getWhitelist(novelId))

  const handleDismissDriftTerm = useCallback((term: string) => {
    addToWhitelist(novelId, term)
    setDriftWhitelist(prev => [...prev, term])
  }, [novelId])

  // Active warnings for this chapter (used in both read and edit mode)
  const activeChapterWarnings = (() => {
    if (activeChapterNum === null) return []
    return getActiveWarnings(novelId, activeChapterNum, currentMeta?.created_at)
      .filter(w => !driftWhitelist.includes(w.term))
  })()

  // Read-mode: full annotations with popovers
  const chapterDriftAnnotations: TextAnnotation[] = (() => {
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
  })()

  // Edit-mode: compact term list for the editor banner
  const editorWarningTerms = editMode && activeChapterWarnings.length > 0
    ? activeChapterWarnings.map(w => ({ code: w.code, term: w.term }))
    : undefined

  const filteredChapters = (() => {
    if (!searchQuery.trim()) return chaptersMeta
    return chaptersMeta.filter((chapterMeta) => matchesChapterSearch(chapterMeta, searchQuery))
  })()

  useEffect(() => {
    // Prevent autosave timers from leaking across chapter switches.
    cancelAutoSave()
  }, [activeChapterNum, cancelAutoSave, location.key, novelId])

  const handleEditorChange = (val: string) => {
    editorSaveGenerationRef.current += 1
    setEditorSaveError(null)
    setEditorContent(val)
    scheduleAutoSave(val)
  }
  const handleSave = () => {
    if (activeChapterNum === null) return
    void saveCurrentEditorNow()
      .then((isCurrentSave) => {
        if (isCurrentSave) setEditMode(false)
      })
      .catch(() => {
        // Keep the editor open; user can retry.
      })
  }
  const handleCancelEdit = () => {
    editorSaveGenerationRef.current += 1
    cancelAutoSave()
    setEditorContent(chapter?.content ?? '')
    setEditorSaveError(null)
    setEditMode(false)
  }
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
  const handleCreateChapter = () => {
    const targetNovelId = novelId
    const targetLocationKey = location.key
    const createGeneration = chapterCreateGenerationRef.current + 1
    chapterCreateGenerationRef.current = createGeneration
    setChapterCreateError(null)
    createChapter.mutate({ title: '', content: '' }, {
      onSuccess: (nc) => {
        if (
          chapterCreateNovelContextRef.current.novelId !== targetNovelId
          || chapterCreateNovelContextRef.current.locationKey !== targetLocationKey
          || chapterCreateGenerationRef.current !== createGeneration
        ) {
          return
        }
        editorSaveGenerationRef.current += 1
        cancelAutoSave()
        setEditorContent('')
        setEditorSaveError(null)
        setEditingTitle(false)
        setEditMode(true)
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
  }
  const handleTitleSave = () => {
    setEditingTitle(false)
    if (activeChapterNum === null || !currentMeta) return
    const newTitle = titleDraft.trim()
    if (newTitle === (currentMeta.title || '')) return
    updateChapter.mutate({ title: newTitle })
  }

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
        editorSaveGenerationRef.current += 1
        cancelAutoSave()
        // Clean up persisted drift warnings for the deleted chapter
        setActiveWarnings(novelId, activeChapterNum, [])
        const idx = chaptersMeta.findIndex(c => c.chapter_number === activeChapterNum)
        const next = chaptersMeta[idx + 1] ?? chaptersMeta[idx - 1]
        setEditorContent('')
        setEditMode(false)
        setEditingTitle(false)
        setShowMoreActions(false)
        navigateToChapterStage(next?.chapter_number ?? null)
      },
    })
  }

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorInfo, setCursorInfo] = useState({ para: 1, col: 1 })
  const handleSelectionChange = () => {
    const ta = textareaRef.current; if (!ta) return
    const before = ta.value.slice(0, ta.selectionStart); const lines = before.split('\n')
    setCursorInfo({ para: lines.length, col: lines[lines.length - 1].length + 1 })
  }
  const handleUndo = () => { textareaRef.current?.focus(); document.execCommand('undo') }
  const handleRedo = () => { textareaRef.current?.focus(); document.execCommand('redo') }

  const windowIndexStatusMeta = getWindowIndexCopilotStatusMeta(novel?.window_index ?? null, locale)
  const {
    activeArtifactPanelState,
    applyActiveArtifactContextSearchParams,
    atlasStudioOrigin,
    effectiveResultsProvenance,
    handleResultsDebugChange,
    hasResultsContext,
    injectionSummaryPanelState,
    resultsDebug,
    resultsNavigationState,
    setInjectionSummaryCategory,
    showInjectionSummaryRail,
    toggleInjectionSummaryRail,
    closeInjectionSummaryRail,
  } = useStudioArtifactState({
    novelId,
    activeStage,
    activeChapterNum,
    routeState,
    location,
    searchParams,
    navigate,
  })

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

  const navigateToChapterStage = useCallback((chapterNumber: number | null = null) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), chapterNumber)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    const nextSearch = nextSearchParams.toString()
    navigate(nextSearch ? `/novel/${novelId}?${nextSearch}` : `/novel/${novelId}`, { replace: true, state: null })
  }, [applyWorldEntryRouteSearchParams, navigate, novelId])
  const navigateToResultsStage = useCallback((options?: { replace?: boolean }) => {
    let nextSearchParams = setStudioResultsStageSearchParams(new URLSearchParams(), activeChapterNum)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    if (effectiveResultsProvenance) {
      nextSearchParams.set('continuations', effectiveResultsProvenance.continuations)
      if (effectiveResultsProvenance.totalVariants !== null) {
        nextSearchParams.set('total_variants', String(effectiveResultsProvenance.totalVariants))
      } else {
        nextSearchParams.delete('total_variants')
      }
    } else {
      nextSearchParams.delete('continuations')
      nextSearchParams.delete('total_variants')
    }
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, activeArtifactPanelState)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, {
      replace: options?.replace ?? false,
      state: resultsNavigationState,
    })
  }, [activeArtifactPanelState, activeChapterNum, applyWorldEntryRouteSearchParams, effectiveResultsProvenance, navigate, novelId, resultsNavigationState])
  const navigateToWriteStage = useCallback(() => {
    let nextSearchParams = setStudioStageSearchParams(new URLSearchParams(), 'write')
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: true, state: null })
  }, [applyWorldEntryRouteSearchParams, navigate, novelId])
  const navigateToEntityStage = useCallback((entityId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioEntityStageSearchParams(nextSearchParams, entityId)
    nextSearchParams = applyActiveArtifactContextSearchParams(nextSearchParams)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, applyActiveArtifactContextSearchParams, applyWorldEntryRouteSearchParams, navigate, novelId, resultsNavigationState])
  const navigateToReviewStage = useCallback((reviewKind: 'entities' | 'relationships' | 'systems', options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioReviewKindSearchParams(nextSearchParams, reviewKind)
    nextSearchParams = applyActiveArtifactContextSearchParams(nextSearchParams)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, applyActiveArtifactContextSearchParams, applyWorldEntryRouteSearchParams, navigate, novelId, resultsNavigationState])
  const navigateToRelationshipStage = useCallback((entityId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioRelationshipStageSearchParams(nextSearchParams, entityId)
    nextSearchParams = applyActiveArtifactContextSearchParams(nextSearchParams)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, applyActiveArtifactContextSearchParams, applyWorldEntryRouteSearchParams, navigate, novelId, resultsNavigationState])
  const navigateToSystemStage = useCallback((systemId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioSystemStageSearchParams(nextSearchParams, systemId)
    nextSearchParams = applyActiveArtifactContextSearchParams(nextSearchParams)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, applyActiveArtifactContextSearchParams, applyWorldEntryRouteSearchParams, navigate, novelId, resultsNavigationState])
  const navigateToAtlas = useCallback((params?: URLSearchParams) => {
    warmAtlasAssist()

    const commitNavigation = () => {
      let nextParams = applyWorldEntryRouteSearchParams(params ?? new URLSearchParams())
      nextParams = setAtlasStudioOriginSearchParams(nextParams, atlasStudioOrigin)
      const nextSearch = nextParams.toString()
      navigate(nextSearch ? `/world/${novelId}?${nextSearch}` : `/world/${novelId}`)
    }

    if (editMode) {
      void saveCurrentEditorNow()
        .then((isCurrentSave) => {
          if (!isCurrentSave) return
          setEditMode(false)
          commitNavigation()
        })
        .catch(() => {
          // Save failed — stay on the current Studio stage so the user can retry.
        })
      return
    }

    commitNavigation()
  }, [applyWorldEntryRouteSearchParams, atlasStudioOrigin, editMode, navigate, novelId, saveCurrentEditorNow, warmAtlasAssist])
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

  const handleToggleAssist = useCallback(() => {
    setAssistOpen(current => !current)
  }, [])

  const assistRailPinnedOpen = (
    resolveStudioWorldEntryStage({
      worldEntityCount: worldEntities.length,
      worldSystemCount: worldSystems.length,
      handoff: worldEntryHandoff,
      pending: worldEntryPending,
    }) !== 'routine'
  )
  const showAssistRail = assistOpen || assistRailPinnedOpen

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

  const wordCount = countWords(editMode ? editorContent : (chapter?.content ?? ''))
  const currentChapterIdentity = chapter ?? currentMeta ?? null
  const displayTitle = currentChapterIdentity ? getChapterDisplayTitle(currentChapterIdentity.title) : ''
  const activeChapterReference = currentChapterIdentity ? formatChapterBadgeLabel(currentChapterIdentity) : null
  const showEntryStage = visiblePreparationGate !== null || showWorldOnboarding

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="min-h-0 flex-1 overflow-hidden">
      {showEntryStage ? (
        <StudioOnboardingStage
          novelId={novelId}
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
          worldGenOpen={worldGenOpen}
          onWorldGenOpenChange={setWorldGenOpen}
          onTriggerBootstrap={handleTriggerBootstrap}
          onDismissWorldOnboarding={handleDismissWorldOnboarding}
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
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
          <NovelShellLayout className="flex-1 min-h-0 gap-3 overflow-hidden p-0">
            <NovelShellRail className="w-[280px]">
              <StudioNavigationRail
                novelTitle={novel.title}
                searchQuery={searchQuery}
                onSearchQueryChange={setSearchQuery}
                chapters={filteredChapters.map(c => ({
                  chapterNumber: c.chapter_number,
                  label: formatChapterLabel(c),
                }))}
                selectedChapterNumber={activeChapterNum}
                onSelectChapter={(chapterNumber) => {
                  editorSaveGenerationRef.current += 1
                  cancelAutoSave()
                  setEditorSaveError(null)
                  setEditingTitle(false)
                  setEditorContent('')
                  setEditMode(false)
                  setShowMoreActions(false)
                  navigateToChapterStage(chapterNumber)
                }}
                chapterCount={chaptersMeta.length}
                onCreateChapter={handleCreateChapter}
                isCreating={createChapter.isPending}
                latestChapterReference={latestChapterReference}
                onContinuation={() => {
                  // Save-first: if editing, flush autosave before switching stage
                  if (editMode) {
                    saveCurrentEditorNow()
                      .then((isCurrentSave) => {
                        if (!isCurrentSave) return
                        setEditMode(false)
                        navigateToWriteStage()
                      })
                      .catch(() => {
                        // Save failed — stay on chapter stage, user can retry
                      })
                  } else {
                    navigateToWriteStage()
                  }
                }}
                onOpenAtlas={() => {
                  setShowMoreActions(false)
                  navigateToAtlas()
                }}
                onWarmAtlas={warmAtlasAssist}
                activeStage={activeStage}
              />
            </NovelShellRail>

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
                  onToggleAssist={handleToggleAssist}
                />
              </div>
            ) : null}

            {activeStage === 'results' ? null : activeStage === 'write' && latestChapterNum !== null ? (
              /* ── Write Stage ── */
              <ContinuationSetupStage
                novelId={novelId}
                contentFormat={novel.content_format}
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
                onToggleAssist={handleToggleAssist}
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
                  onToggleAssist={handleToggleAssist}
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
                onToggleAssist={handleToggleAssist}
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
                  onToggleAssist={handleToggleAssist}
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
                onToggleAssist={handleToggleAssist}
              />
            ) : (
              /* ── Chapter Stage ── */
              <div className="flex-1 min-w-0 flex flex-col gap-6 px-8 py-8 lg:px-16 overflow-hidden">
                {/* Action Bar */}
                <div className="shrink-0 border-b border-[var(--nw-glass-border)] pb-5">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1 space-y-3">
                      {currentMeta ? (
                        <>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] font-medium text-foreground/88">
                              {formatChapterBadgeLabel(currentChapterIdentity ?? currentMeta)}
                            </span>
                            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                              {editMode ? t('studio.chapter.editing') : t('studio.chapter.reading')}
                            </span>
                          </div>

                          <div className="min-w-0">
                            {editingTitle ? (
                              <input
                                autoFocus
                                value={titleDraft}
                                onChange={e => setTitleDraft(e.target.value)}
                                onBlur={() => { handleTitleSave() }}
                                onKeyDown={e => { if (e.key === 'Enter') handleTitleSave(); if (e.key === 'Escape') setEditingTitle(false) }}
                                className="w-full max-w-[720px] font-mono text-[22px] font-semibold text-foreground bg-[var(--nw-glass-bg)] border border-[hsl(var(--accent)/0.35)] rounded-md px-2 py-1 outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0"
                                placeholder={t('studio.chapter.titlePlaceholder')}
                              />
                            ) : (
                              <div
                                onDoubleClick={() => { setTitleDraft(displayTitle); setEditingTitle(true) }}
                                title={t('studio.chapter.titleEditHint')}
                                className="cursor-text"
                              >
                                {displayTitle ? (
                                  <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground break-words">
                                    {displayTitle}
                                  </h1>
                                ) : (
                                  <span className="text-[22px] text-muted-foreground italic">{t('studio.chapter.titleAddHint')}</span>
                                )}
                              </div>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                            <span>{t('studio.chapter.charCount', { count: wordCount.toLocaleString() })}</span>
                            {currentMeta.created_at ? (
                              <span>{t('studio.chapter.updated', { time: formatRelativeTime(currentMeta.created_at) })}</span>
                            ) : null}
                          </div>
                        </>
                      ) : (
                        <div className="space-y-2">
                          <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                            {t('studio.header.workspace')}
                          </span>
                          <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground">
                            {t('studio.header.selectChapter')}
                          </h1>
                        </div>
                      )}
                    </div>

                    <div className="flex w-full flex-col gap-2.5 xl:w-auto xl:max-w-[520px] xl:items-end">
                      <div className="flex flex-wrap gap-2">
                        <NwButton
                          onClick={() => {
                            if (activeChapterNum === null) return
                            editorSaveGenerationRef.current += 1
                            if (!editMode) {
                              setEditorContent(chapter?.content ?? '')
                              cancelAutoSave()
                              setEditorSaveError(null)
                            } else {
                              cancelAutoSave()
                              setEditorSaveError(null)
                            }
                            setEditMode(!editMode)
                          }}
                          disabled={activeChapterNum === null}
                          variant="accentOutline"
                          className="rounded-[10px] px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
                        >
                          <Pencil size={14} />
                          {t('studio.chapter.edit')}
                        </NwButton>

                        <div className="relative">
                          <NwButton
                            onClick={() => setShowMoreActions((prev) => !prev)}
                            variant="glass"
                            className="h-10 w-10 rounded-[10px] p-0 text-sm font-medium"
                            aria-haspopup="menu"
                            aria-expanded={showMoreActions}
                            aria-label={t('studio.actions.moreActions')}
                            title={t('studio.actions.moreActions')}
                          >
                            <MoreHorizontal size={14} />
                          </NwButton>

                          {showMoreActions ? (
                            <>
                              <div
                                className="fixed inset-0 z-10"
                                onClick={() => setShowMoreActions(false)}
                              />
                              <GlassSurface
                                variant="floating"
                                className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[188px] rounded-[16px] p-1.5"
                              >
                                <button
                                  type="button"
                                  onClick={() => {
                                    setShowMoreActions(false)
                                    handleExportChapter()
                                  }}
                                  className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
                                >
                                  <Upload size={14} className="text-muted-foreground" />
                                  <span>{t('studio.actions.exportChapter')}</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setShowMoreActions(false)
                                    handleExportAll()
                                  }}
                                  className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
                                >
                                  <Upload size={14} className="text-muted-foreground" />
                                  <span>{t('studio.actions.exportAllChapters')}</span>
                                </button>

                                {activeChapterNum !== null && chaptersMeta.length > 1 ? (
                                  <>
                                    <div className="mx-2 my-1 h-px bg-[var(--nw-glass-border)]" />
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setShowMoreActions(false)
                                        void handleDeleteChapter()
                                      }}
                                      className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-[hsl(var(--color-danger))] transition-colors hover:bg-[hsl(var(--color-danger)/0.10)]"
                                    >
                                      <Trash2 size={14} />
                                      <span>{t('studio.chapter.delete')}</span>
                                    </button>
                                  </>
                                ) : null}
                              </GlassSurface>
                            </>
                          ) : null}
                        </div>

                        <AssistToggleButton active={showAssistRail} onClick={handleToggleAssist} />
                      </div>
                    </div>
                  </div>
                </div>

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
            <Suspense fallback={<NovelCopilotDrawerFallback width={drawerWidth} />}>
              <NovelCopilotDrawer novelId={novelId} onLocateTarget={handleStudioLocateTarget} />
            </Suspense>
          ) : showInjectionSummaryRail && resultsDebug ? (
            <NovelShellRail className="w-[360px]">
              <InjectionSummaryPanel
                debug={resultsDebug}
                activeCategory={injectionSummaryPanelState?.injectionCategory ?? undefined}
                onActiveCategoryChange={setInjectionSummaryCategory}
                onClose={closeInjectionSummaryRail}
                onOpenAtlas={handleOpenInjectionCategory}
                onWarmAtlas={warmAtlasAssist}
                onSelectItem={handleOpenInjectionItem}
              />
            </NovelShellRail>
          ) : showAssistRail ? (
            <StudioSupportRail
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
          ) : null}
          </NovelShellLayout>
        </div>
      )}
      <ConfirmDialog {...confirmDialogProps} />
    </PageShell>
  )
}
