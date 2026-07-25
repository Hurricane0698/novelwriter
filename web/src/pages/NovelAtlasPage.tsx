// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense, useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { AtlasShell } from '@/components/atlas/AtlasShell'
import { EntityNavigator } from '@/components/atlas/entities/EntityNavigator'
import { SystemsWorkspace } from '@/components/atlas/systems/SystemsWorkspace'
import { RelationshipsTab } from '@/components/world-model/relationships/RelationshipsTab'
import { DraftReviewSummaryCard, type DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'
import { RelationshipSidebarPanel } from '@/components/atlas/relationships/RelationshipSidebarPanel'
import { ArtifactStage } from '@/components/novel-shell/ArtifactStage'
import { NovelShellLayout } from '@/components/novel-shell/NovelShellLayout'
import { useNovelShell } from '@/components/novel-shell/NovelShellContext'
import {
  buildStudioHostPath,
  readWorldEntryHandoffSearchParams,
  readWorldEntryPendingSearchParams,
  readAtlasStudioOriginSearchParams,
  setAtlasEntitySearchParams,
  setAtlasHighlightSearchParams,
  setAtlasRelationshipSearchParams,
  setAtlasReviewKindSearchParams,
  setAtlasSystemSearchParams,
  setAtlasTabSearchParams,
  setWorldEntryHandoffSearchParams,
  setWorldEntryPendingSearchParams,
  type AtlasWorkbenchTab,
} from '@/components/novel-shell/NovelShellRouteState'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { useBootstrapStatus } from '@/hooks/world/useBootstrap'
import { useDraftReviewBacklog } from '@/hooks/world/useDraftReviewBacklog'
import { LABELS } from '@/constants/labels'
import { NovelCopilotDrawerFallback } from '@/components/novel-copilot/NovelCopilotDrawerFallback'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { useAtlasCopilotTargetNavigation } from '@/components/novel-copilot/useCopilotTargetNavigation'
import { MIN_NOVEL_SHELL_DRAWER_WIDTH } from '@/components/novel-shell/novelShellChromeState'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { isSeededDemoNovel } from '@/lib/demoProject'
import { getWindowIndexPollingInterval } from '@/lib/windowIndexStatus'
import {
  countVisitedDemoFirstWritingOnboardingSteps,
  getDemoFirstWritingOnboardingState,
  markDemoFirstWritingOnboardingStepVisited,
} from '@/lib/demoFirstOnboardingStorage'
import {
  isWorldEntryPendingExpired,
  resolvePendingWorldEntryHandoffFromBootstrapJob,
} from '@/lib/worldEntryHandoff'
import { normalizeWorldEntryHandoff } from '@/lib/worldEntryReview'
import { copilotDrawerShellClassName } from '@/components/novel-copilot/novelCopilotChrome'
import { cn } from '@/lib/utils'
import { loadAtlasAssistWorkbench, scheduleAtlasAssistWorkbenchPrefetch } from '@/components/atlas/workbench/atlasAssistWorkbenchLoader'
import {
  loadNovelCopilotDrawer,
  scheduleNovelCopilotDrawerPrefetch,
} from '@/components/novel-copilot/novelCopilotDrawerLoader'

const ATLAS_MIN_MAIN_STAGE_WIDTH = 760
const ATLAS_ASSIST_OVERLAY_MAX_WIDTH = 420
const ATLAS_ASSIST_OVERLAY_MARGIN_PX = 24
const AtlasAssistWorkbench = lazy(async () => {
  const mod = await loadAtlasAssistWorkbench()
  return { default: mod.AtlasAssistWorkbench }
})
const NovelCopilotDrawer = lazy(async () => {
  const mod = await loadNovelCopilotDrawer()
  return { default: mod.NovelCopilotDrawer }
})
const EntityDetail = lazy(async () => {
  const mod = await import('@/components/world-model/entities/EntityDetail')
  return { default: mod.EntityDetail }
})
const DraftReviewNavigator = lazy(async () => {
  const mod = await import('@/components/atlas/review/DraftReviewNavigator')
  return { default: mod.DraftReviewNavigator }
})
const DraftReviewTab = lazy(async () => {
  const mod = await import('@/components/world-model/shared/DraftReviewTab')
  return { default: mod.DraftReviewTab }
})

function parseOptionalNumber(raw: string | null) {
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

function AtlasAssistWorkbenchFallback({
  width,
}: {
  width: number
}) {
  return (
    <aside
      className={cn(
        'relative shrink-0 overflow-hidden border-l',
        copilotDrawerShellClassName,
      )}
      style={{ width }}
      data-testid="atlas-assist-workbench-fallback"
      aria-label="Loading Atlas assist"
    >
      <div className="absolute inset-0 bg-[var(--nw-copilot-shell-bg)]" />
      <div className="relative flex h-full flex-col px-4 py-5">
        <div className="h-16 rounded-[18px] border border-[var(--nw-copilot-border)] bg-background/12" />
        <div className="mt-4 space-y-4">
          <div className="h-40 rounded-[24px] border border-[var(--nw-copilot-border)] bg-background/10" />
          <div className="h-48 rounded-[24px] border border-[var(--nw-copilot-border)] bg-background/10" />
        </div>
      </div>
    </aside>
  )
}

function AtlasEntityDetailFallback() {
  return (
    <div
      className="flex-1 min-h-0 h-full overflow-y-auto"
      data-testid="atlas-entity-detail-fallback"
      aria-label="Loading entity detail"
    >
      <div className="mx-auto max-w-5xl space-y-4 px-8 py-8">
        <div className="h-8 w-56 rounded bg-[hsl(var(--foreground)/0.12)]" />
        <div className="h-28 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
        <div className="h-40 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
      </div>
    </div>
  )
}

function DraftReviewNavigatorFallback() {
  return (
    <div
      className="shrink-0 flex h-full min-h-0 w-[280px] flex-col overflow-hidden border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]"
      data-testid="draft-review-navigator-fallback"
      aria-label="Loading review navigator"
    >
      <div className="space-y-3 p-4">
        <div className="h-5 w-32 rounded bg-[hsl(var(--foreground)/0.10)]" />
        <div className="h-9 rounded-xl border border-[var(--nw-glass-border)] bg-transparent" />
      </div>
      <div className="space-y-2 px-2 pb-3">
        <div className="h-14 rounded-xl bg-[hsl(var(--foreground)/0.06)]" />
        <div className="h-14 rounded-xl bg-[hsl(var(--foreground)/0.06)]" />
        <div className="h-14 rounded-xl bg-[hsl(var(--foreground)/0.06)]" />
      </div>
    </div>
  )
}

function DraftReviewTabFallback() {
  return (
    <div
      className="flex-1 min-w-0 overflow-hidden p-4"
      data-testid="draft-review-tab-fallback"
      aria-label="Loading review content"
    >
      <div className="space-y-3">
        <div className="h-24 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
        <div className="h-24 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
        <div className="h-24 rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)]" />
      </div>
    </div>
  )
}

export function NovelAtlasPage() {
  const { t } = useUiLocale()
  const { novelId } = useParams<{ novelId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { routeState, shellState } = useNovelShell()
  const { drawerWidth, setDrawerWidth } = shellState
  const copilot = useNovelCopilot()
  const { isOpen: copilotIsOpen, closeDrawer: closeCopilot } = copilot
  const containerRef = useRef<HTMLDivElement>(null)
  const nid = Number(novelId)
  const invalidNovelId = Number.isNaN(nid)
  const studioOrigin = useMemo(() => readAtlasStudioOriginSearchParams(searchParams), [searchParams])
  const worldEntryHandoff = useMemo(() => readWorldEntryHandoffSearchParams(searchParams), [searchParams])
  const worldEntryPending = useMemo(() => readWorldEntryPendingSearchParams(searchParams), [searchParams])
  const studioReturnPath = useMemo(() => {
    const basePath = studioOrigin ? buildStudioHostPath(nid, studioOrigin) : `/novel/${nid}`
    const url = new URL(basePath, 'https://novwr.local')
    let nextSearchParams = new URLSearchParams(url.search)
    nextSearchParams = setWorldEntryHandoffSearchParams(nextSearchParams, worldEntryHandoff)
    nextSearchParams = setWorldEntryPendingSearchParams(nextSearchParams, worldEntryPending)
    const nextSearch = nextSearchParams.toString()
    return `${url.pathname}${nextSearch ? `?${nextSearch}` : ''}`
  }, [nid, studioOrigin, worldEntryHandoff, worldEntryPending])
  const [reviewSearch, setReviewSearch] = useState('')
  const [reviewHighlight, setReviewHighlight] = useState<number | null>(null)
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const trackedWorldModelViewRef = useRef(false)
  const [assistOpen, setAssistOpen] = useState(true)
  const [assistDockMode, setAssistDockMode] = useState<'rail' | 'overlay'>('rail')
  const [assistRenderWidth, setAssistRenderWidth] = useState(drawerWidth)
  const assistVisible = assistOpen || copilotIsOpen
  const handleReviewSelect = useCallback((kind: DraftReviewKind, id: number) => {
    setReviewHighlight(id)
    setSearchParams((prev) => setAtlasHighlightSearchParams(setAtlasReviewKindSearchParams(prev, kind), id), {
      replace: true,
    })
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    highlightTimerRef.current = setTimeout(() => setReviewHighlight(null), 2500)
  }, [setSearchParams])
  const [relCreateOpen, setRelCreateOpen] = useState(false)
  const { data: novel } = useQuery({
    queryKey: novelKeys.detail(nid),
    queryFn: () => api.getNovel(nid),
    enabled: !invalidNovelId,
    refetchInterval: (query) => getWindowIndexPollingInterval(query.state.data?.window_index ?? null),
  })
  const { data: bootstrapJob } = useBootstrapStatus(nid, {
    refetchWhenMissing: novel?.window_index?.ingest?.bootstrap_plan != null,
  })
  const {
    totalDrafts,
    isResolved: isDraftBacklogResolved,
  } = useDraftReviewBacklog(nid)

  // Narrow-desktop fallback: keep Atlas assist reachable by switching from docked rail to overlay.
  useEffect(() => {
    if (!assistVisible || !containerRef.current) return
    const el = containerRef.current
    const checkWidth = () => {
      const maxDrawerWidth = el.clientWidth - ATLAS_MIN_MAIN_STAGE_WIDTH
      if (maxDrawerWidth < MIN_NOVEL_SHELL_DRAWER_WIDTH) {
        setAssistDockMode('overlay')
        setAssistRenderWidth(
          Math.min(
            drawerWidth,
            ATLAS_ASSIST_OVERLAY_MAX_WIDTH,
            Math.max(el.clientWidth - ATLAS_ASSIST_OVERLAY_MARGIN_PX * 2, 0),
          ),
        )
        if (copilotIsOpen) closeCopilot()
        return
      }

      setAssistDockMode('rail')
      setAssistRenderWidth(Math.min(drawerWidth, maxDrawerWidth))
      if (drawerWidth > maxDrawerWidth) {
        setDrawerWidth(maxDrawerWidth)
      }
    }
    checkWidth()
    const observer = new ResizeObserver(checkWidth)
    observer.observe(el)
    return () => observer.disconnect()
  }, [assistVisible, closeCopilot, copilotIsOpen, drawerWidth, setDrawerWidth])

  useEffect(() => {
    if (assistVisible && !copilotIsOpen) return
    return scheduleAtlasAssistWorkbenchPrefetch()
  }, [assistVisible, copilotIsOpen])

  useEffect(() => {
    return scheduleNovelCopilotDrawerPrefetch()
  }, [])
  const { data: entities = [] } = useWorldEntities(nid)
  const { data: systems = [] } = useWorldSystems(nid)
  const selectedEntityId = routeState.entityId
  const selectedSystemId = routeState.systemId
  const selectedStillExists =
    selectedEntityId !== null && entities.some((entity) => entity.id === selectedEntityId)
  const effectiveSelectedEntityId =
    selectedEntityId === null ? null : selectedStillExists ? selectedEntityId : (entities[0]?.id ?? null)
  const effectiveSelectedEntityName =
    effectiveSelectedEntityId === null
      ? null
      : entities.find((entity) => entity.id === effectiveSelectedEntityId)?.name ?? null
  const selectedSystemStillExists =
    selectedSystemId !== null && systems.some((system) => system.id === selectedSystemId)
  const effectiveSelectedSystemId =
    selectedSystemId === null ? null : selectedSystemStillExists ? selectedSystemId : (systems[0]?.id ?? null)

  const tab: AtlasWorkbenchTab = routeState.worldTab ?? 'systems'
  const reviewKind: DraftReviewKind = routeState.reviewKind ?? 'entities'
  const highlightedRelationshipId = useMemo(
    () => parseOptionalNumber(searchParams.get('relationship')),
    [searchParams],
  )
  const reviewHighlightFromUrl = useMemo(
    () => parseOptionalNumber(searchParams.get('highlight')),
    [searchParams],
  )
  const effectiveReviewHighlight = reviewHighlightFromUrl ?? reviewHighlight

  useEffect(() => {
    if (invalidNovelId || trackedWorldModelViewRef.current) return
    trackedWorldModelViewRef.current = true
    void trackHostedAnalyticsEvent('world_model_view', {
      novelId: nid,
      meta: { surface: 'atlas', tab },
    })
  }, [invalidNovelId, nid, tab])

  useEffect(() => {
    if (invalidNovelId || !isSeededDemoNovel(novel)) return
    const previous = getDemoFirstWritingOnboardingState(nid, novel?.created_at)
    if (previous.visited.atlas) return
    const next = markDemoFirstWritingOnboardingStepVisited(nid, novel?.created_at, 'atlas')
    const progressCount = countVisitedDemoFirstWritingOnboardingSteps(next)
    void trackHostedAnalyticsEvent('demo_guide_step_complete', {
      novelId: nid,
      meta: {
        step: 'atlas',
        progress_count: progressCount,
      },
    })
    if (previous.status !== 'completed' && next.status === 'completed') {
      void trackHostedAnalyticsEvent('demo_guide_completed', {
        novelId: nid,
        meta: {
          progress_count: progressCount,
        },
      })
    }
  }, [invalidNovelId, nid, novel])

  const setSelectedEntity = useCallback((entityId: number | null) => {
    setSearchParams((prev) => {
      const next = setAtlasEntitySearchParams(prev, entityId)
      return setAtlasRelationshipSearchParams(next, null)
    }, { replace: true })
  }, [setSearchParams])

  const openAtlasEntityTab = useCallback((nextTab: 'entities' | 'relationships', entityId: number | null) => {
    if (nextTab !== 'relationships') setRelCreateOpen(false)
    setSearchParams((prev) => {
      let next = setAtlasTabSearchParams(prev, nextTab)
      next = setAtlasEntitySearchParams(next, entityId)
      return setAtlasRelationshipSearchParams(next, null)
    }, { replace: true })
  }, [setSearchParams])

  const openAtlasSystemTab = useCallback((systemId: number | null) => {
    setSearchParams((prev) => {
      const next = setAtlasTabSearchParams(prev, 'systems')
      return setAtlasSystemSearchParams(next, systemId)
    }, { replace: true })
  }, [setSearchParams])

  const handleTabChange = useCallback((next: AtlasWorkbenchTab) => {
    if (next !== 'relationships') setRelCreateOpen(false)
    setSearchParams((prev) => {
      return setAtlasTabSearchParams(prev, next)
    }, { replace: true })
  }, [setSearchParams])

  const openDraftReview = useCallback((kind?: DraftReviewKind) => {
    setReviewSearch('')
    setReviewHighlight(null)
    setSearchParams((prev) => {
      return setAtlasReviewKindSearchParams(prev, kind ?? reviewKind)
    }, { replace: true })
  }, [reviewKind, setSearchParams])

  const openDraftReviewWithHistory = useCallback((kind?: DraftReviewKind) => {
    setReviewSearch('')
    setReviewHighlight(null)
    setSearchParams((prev) => {
      return setAtlasReviewKindSearchParams(prev, kind ?? reviewKind)
    }, { replace: false })
  }, [reviewKind, setSearchParams])

  const setAtlasWorldEntryHandoff = useCallback((handoff: ReturnType<typeof readWorldEntryHandoffSearchParams>) => {
    setSearchParams((prev) => {
      let next = setWorldEntryHandoffSearchParams(prev, handoff)
      if (handoff) next = setWorldEntryPendingSearchParams(next, null)
      return next
    }, { replace: true })
  }, [setSearchParams])

  const setAtlasWorldEntryPending = useCallback((pending: ReturnType<typeof readWorldEntryPendingSearchParams>) => {
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

  useEffect(() => {
    if (!isDraftBacklogResolved) return
    const normalizedHandoff = normalizeWorldEntryHandoff(worldEntryHandoff, {
      reviewBacklogCount: totalDrafts,
    })
    if (
      normalizedHandoff?.kind === worldEntryHandoff?.kind
      && normalizedHandoff?.entityCount === worldEntryHandoff?.entityCount
      && normalizedHandoff?.relationshipCount === worldEntryHandoff?.relationshipCount
      && normalizedHandoff?.systemCount === worldEntryHandoff?.systemCount
    ) {
      return
    }
    setAtlasWorldEntryHandoff(normalizedHandoff)
  }, [
    isDraftBacklogResolved,
    setAtlasWorldEntryHandoff,
    totalDrafts,
    worldEntryHandoff,
  ])

  const handleReviewKindChange = useCallback((kind: DraftReviewKind) => {
    setReviewHighlight(null)
    setSearchParams((prev) => {
      return setAtlasReviewKindSearchParams(prev, kind)
    }, { replace: true })
  }, [setSearchParams])

  const handleLocateCopilotTarget = useAtlasCopilotTargetNavigation({
    onBeforeNavigate: (target) => {
      if (target.tab !== 'relationships') setRelCreateOpen(false)
    },
    onBeforeReviewTarget: () => {
      setReviewSearch('')
    },
  })

  const handleToggleCopilot = useCallback(() => {
    if (assistDockMode === 'overlay') {
      if (copilotIsOpen) closeCopilot()
      setAssistOpen((current) => !assistVisible ? true : !current)
      return
    }

    if (assistVisible) {
      if (copilotIsOpen) closeCopilot()
      setAssistOpen(false)
      return
    }

    setAssistOpen(true)
    if (copilot.sessions.length > 0) {
      copilot.reopenDrawer()
    }
  }, [assistDockMode, assistVisible, closeCopilot, copilot, copilotIsOpen])

  if (invalidNovelId) return <div className="p-4 text-muted-foreground">Novel not found</div>

  return (
    <AtlasShell>
      <div ref={containerRef} className="flex-1 min-h-0 flex flex-col overflow-hidden relative">
        <NovelShellLayout>
          <ArtifactStage>
            <Tabs
              value={tab}
              onValueChange={(next) => handleTabChange(next as AtlasWorkbenchTab)}
              className="flex-1 min-w-0 flex flex-col overflow-hidden"
            >
              <div className="shrink-0 border-b border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl px-4 flex items-center h-12">
                <div className="shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground"
                    onClick={() => navigate(studioReturnPath ?? `/novel/${nid}`)}
                  >
                    <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
                    {t('worldModel.atlas.returnToStudio')}
                  </Button>
                </div>

                <div className="flex-1 flex justify-center self-stretch">
                  <TabsList className="bg-transparent h-full p-0 gap-6">
                    <TabsTrigger value="systems" className="rounded-none border-b-2 border-transparent text-muted-foreground hover:text-foreground/70 data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 h-full" data-testid="tab-systems">
                      {LABELS.TAB_SYSTEMS}
                    </TabsTrigger>
                    <TabsTrigger value="entities" className="rounded-none border-b-2 border-transparent text-muted-foreground hover:text-foreground/70 data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 h-full" data-testid="tab-entities">
                      {LABELS.TAB_ENTITIES}
                    </TabsTrigger>
                    <TabsTrigger value="relationships" className="rounded-none border-b-2 border-transparent text-muted-foreground hover:text-foreground/70 data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 h-full" data-testid="tab-relationships">
                      {LABELS.TAB_RELATIONSHIPS}
                    </TabsTrigger>
                    {tab === 'review' ? (
                      <TabsTrigger
                        value="review"
                        className="rounded-none border-b-2 border-transparent text-muted-foreground hover:text-foreground/70 data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 h-full"
                        data-testid="tab-review-indicator"
                      >
                        {t('worldModel.atlas.reviewTab')}
                      </TabsTrigger>
                    ) : null}
                  </TabsList>
                </div>

                <div className="shrink-0 flex items-center">
                  <button
                    type="button"
                    onClick={handleToggleCopilot}
                    onMouseEnter={() => {
                      if (!copilotIsOpen) void loadAtlasAssistWorkbench()
                    }}
                    onFocus={() => {
                      if (!copilotIsOpen) void loadAtlasAssistWorkbench()
                    }}
                    className={`inline-flex items-center justify-center rounded-md h-8 w-8 transition-colors ${
                      assistVisible
                        ? 'bg-[var(--nw-glass-bg-hover)] text-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)]'
                    }`}
                    aria-label="Toggle Copilot"
                  >
                    <Bot className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <TabsContent value="systems" className="flex-1 min-h-0 mt-0 overflow-hidden">
                <SystemsWorkspace
                  novelId={nid}
                  onOpenDraftReview={openDraftReview}
                  selectedId={effectiveSelectedSystemId}
                  onSelectSystem={openAtlasSystemTab}
                />
              </TabsContent>

              <TabsContent value="entities" className="flex-1 min-h-0 flex mt-0 overflow-hidden">
                <EntityNavigator
                  novelId={nid}
                  selectedEntityId={effectiveSelectedEntityId}
                  onSelectEntity={setSelectedEntity}
                  bottomSlot={(
                    <DraftReviewSummaryCard novelId={nid} onOpen={openDraftReview} />
                  )}
                />
                <Suspense fallback={<AtlasEntityDetailFallback />}>
                  <EntityDetail
                    novelId={nid}
                    entityId={effectiveSelectedEntityId}
                    onDeleted={() => setSelectedEntity(null)}
                    copilotSurface="atlas"
                  />
                </Suspense>
              </TabsContent>

              <TabsContent value="relationships" className="flex-1 min-h-0 flex mt-0 overflow-hidden">
                <EntityNavigator
                  novelId={nid}
                  selectedEntityId={effectiveSelectedEntityId}
                  onSelectEntity={setSelectedEntity}
                  bottomSlot={
                    <>
                      <RelationshipSidebarPanel
                        novelId={nid}
                        selectedEntityId={effectiveSelectedEntityId}
                        selectedEntityName={effectiveSelectedEntityName}
                        onRequestNewRelationship={() => setRelCreateOpen(true)}
                        onOpenDraftReview={() => openDraftReview('relationships')}
                        showResearchAction={false}
                      />
                      <DraftReviewSummaryCard novelId={nid} onOpen={openDraftReview} />
                    </>
                  }
                />
                <RelationshipsTab
                  novelId={nid}
                  selectedEntityId={effectiveSelectedEntityId}
                  onSelectEntity={setSelectedEntity}
                  selectedRelationshipId={highlightedRelationshipId}
                  creating={relCreateOpen}
                  onCreatingChange={setRelCreateOpen}
                />
              </TabsContent>

              <TabsContent value="review" className="flex-1 min-h-0 mt-0 overflow-hidden">
                <div className="flex h-full min-h-0 overflow-hidden">
                  <Suspense fallback={<DraftReviewNavigatorFallback />}>
                    <DraftReviewNavigator
                      novelId={nid}
                      kind={reviewKind}
                      onKindChange={handleReviewKindChange}
                      search={reviewSearch}
                      onSearchChange={setReviewSearch}
                      activeItemId={effectiveReviewHighlight}
                      onSelectItem={handleReviewSelect}
                    />
                  </Suspense>
                  <div className="flex-1 min-w-0 overflow-hidden">
                    <Suspense fallback={<DraftReviewTabFallback />}>
                      <DraftReviewTab
                        novelId={nid}
                        kind={reviewKind}
                        onKindChange={handleReviewKindChange}
                        search={reviewSearch}
                        showKindSelector={false}
                        highlightId={effectiveReviewHighlight}
                        onOpenEntity={(id) => {
                          openAtlasEntityTab('entities', id)
                        }}
                        onOpenRelationships={(id) => {
                          openAtlasEntityTab('relationships', id)
                        }}
                        onOpenSystem={(id) => {
                          openAtlasSystemTab(id)
                        }}
                      />
                    </Suspense>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </ArtifactStage>
          {assistVisible && copilotIsOpen ? (
            <Suspense fallback={<NovelCopilotDrawerFallback width={drawerWidth} />}>
              <NovelCopilotDrawer novelId={nid} onLocateTarget={handleLocateCopilotTarget} />
            </Suspense>
          ) : null}
          {assistVisible && !copilotIsOpen && assistDockMode === 'rail' ? (
            <Suspense fallback={<AtlasAssistWorkbenchFallback width={assistRenderWidth} />}>
              <AtlasAssistWorkbench
                novelId={nid}
                tab={tab}
                width={assistRenderWidth}
                onResize={setDrawerWidth}
                selectedEntityId={effectiveSelectedEntityId}
                selectedEntityName={effectiveSelectedEntityName}
                worldEntityCount={entities.length}
                worldSystemCount={systems.length}
                handoff={worldEntryHandoff}
                pending={worldEntryPending}
                onHandoffChange={setAtlasWorldEntryHandoff}
                onPendingHandoffChange={setAtlasWorldEntryPending}
                onOpenDraftReview={openDraftReviewWithHistory}
              />
            </Suspense>
          ) : null}
        </NovelShellLayout>
        {assistVisible && !copilotIsOpen && assistDockMode === 'overlay' ? (
          <div className="pointer-events-none absolute inset-y-0 right-0 z-20 flex items-stretch justify-end p-3 pl-0">
            <div className="pointer-events-auto flex max-w-full pt-12">
              <Suspense fallback={<AtlasAssistWorkbenchFallback width={assistRenderWidth} />}>
                <AtlasAssistWorkbench
                  novelId={nid}
                  tab={tab}
                  width={assistRenderWidth}
                  presentation="overlay"
                  onResize={setDrawerWidth}
                  selectedEntityId={effectiveSelectedEntityId}
                  selectedEntityName={effectiveSelectedEntityName}
                  worldEntityCount={entities.length}
                  worldSystemCount={systems.length}
                  handoff={worldEntryHandoff}
                  pending={worldEntryPending}
                  onHandoffChange={setAtlasWorldEntryHandoff}
                  onPendingHandoffChange={setAtlasWorldEntryPending}
                  onOpenDraftReview={openDraftReviewWithHistory}
                />
              </Suspense>
            </div>
          </div>
        ) : null}
      </div>
    </AtlasShell>
  )
}
