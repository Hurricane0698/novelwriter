// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { AtlasShell } from '@/components/atlas/AtlasShell'
import { EntityNavigator } from '@/components/atlas/entities/EntityNavigator'
import { EntityDetail } from '@/components/world-model/entities/EntityDetail'
import { SystemsWorkspace } from '@/components/atlas/systems/SystemsWorkspace'
import { RelationshipsTab } from '@/components/world-model/relationships/RelationshipsTab'
import { DraftReviewTab } from '@/components/world-model/shared/DraftReviewTab'
import { WorldBuildPanel } from '@/components/world-model/shared/WorldBuildPanel'
import { DraftReviewSummaryCard, type DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'
import { DraftReviewNavigator } from '@/components/atlas/review/DraftReviewNavigator'
import { RelationshipSidebarPanel } from '@/components/atlas/relationships/RelationshipSidebarPanel'
import { ArtifactStage } from '@/components/novel-shell/ArtifactStage'
import { NovelShellLayout } from '@/components/novel-shell/NovelShellLayout'
import { useNovelShell } from '@/components/novel-shell/NovelShellContext'
import {
  buildStudioHostPath,
  readAtlasStudioOriginSearchParams,
  setAtlasEntitySearchParams,
  setAtlasHighlightSearchParams,
  setAtlasRelationshipSearchParams,
  setAtlasReviewKindSearchParams,
  setAtlasSystemSearchParams,
  setAtlasTabSearchParams,
  type AtlasWorkbenchTab,
} from '@/components/novel-shell/NovelShellRouteState'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { LABELS } from '@/constants/labels'
import { NovelCopilotDrawer } from '@/components/novel-copilot/NovelCopilotDrawer'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { buildWholeBookCopilotLaunchArgs } from '@/components/novel-copilot/novelCopilotLauncher'
import { useAtlasCopilotTargetNavigation } from '@/components/novel-copilot/useCopilotTargetNavigation'
import { MIN_NOVEL_SHELL_DRAWER_WIDTH } from '@/components/novel-shell/novelShellChromeState'

const ATLAS_MIN_MAIN_STAGE_WIDTH = 760

function parseOptionalNumber(raw: string | null) {
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

export function NovelAtlasPage() {
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
  const studioReturnPath = studioOrigin ? buildStudioHostPath(nid, studioOrigin) : null
  const [reviewSearch, setReviewSearch] = useState('')
  const [reviewHighlight, setReviewHighlight] = useState<number | null>(null)
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleReviewSelect = useCallback((kind: DraftReviewKind, id: number) => {
    setReviewHighlight(id)
    setSearchParams((prev) => setAtlasHighlightSearchParams(setAtlasReviewKindSearchParams(prev, kind), id), {
      replace: true,
    })
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    highlightTimerRef.current = setTimeout(() => setReviewHighlight(null), 2500)
  }, [setSearchParams])
  const [relCreateOpen, setRelCreateOpen] = useState(false)

  // Narrow-desktop fallback: auto-close copilot when three-zone layout cannot fit
  // (atlas-design-spec §Spatial Zone Contracts — Center Stage min 480px)
  useEffect(() => {
    if (!copilotIsOpen || !containerRef.current) return
    const el = containerRef.current
    const checkWidth = () => {
      const maxDrawerWidth = el.clientWidth - ATLAS_MIN_MAIN_STAGE_WIDTH
      if (maxDrawerWidth < MIN_NOVEL_SHELL_DRAWER_WIDTH) {
        closeCopilot()
        return
      }

      if (drawerWidth > maxDrawerWidth) {
        setDrawerWidth(maxDrawerWidth)
      }
    }
    checkWidth()
    const observer = new ResizeObserver(checkWidth)
    observer.observe(el)
    return () => observer.disconnect()
  }, [closeCopilot, copilotIsOpen, drawerWidth, setDrawerWidth])
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
    if (copilotIsOpen) {
      closeCopilot()
    } else if (copilot.sessions.length > 0) {
      copilot.reopenDrawer()
    } else {
      copilot.openDrawer(...buildWholeBookCopilotLaunchArgs(routeState))
    }
  }, [copilotIsOpen, copilot, closeCopilot, routeState])

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
                    返回工作台
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
                        草稿审核
                      </TabsTrigger>
                    ) : null}
                  </TabsList>
                </div>

                <div className="shrink-0 flex items-center">
                  <button
                    type="button"
                    onClick={handleToggleCopilot}
                    className={`inline-flex items-center justify-center rounded-md h-8 w-8 transition-colors ${
                      copilotIsOpen
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
                    <>
                      <WorldBuildPanel novelId={nid} />
                      <DraftReviewSummaryCard novelId={nid} onOpen={openDraftReview} />
                    </>
                  )}
                />
                <EntityDetail
                  novelId={nid}
                  entityId={effectiveSelectedEntityId}
                  onDeleted={() => setSelectedEntity(null)}
                  copilotSurface="atlas"
                />
              </TabsContent>

              <TabsContent value="relationships" className="flex-1 min-h-0 flex mt-0 overflow-hidden">
                <EntityNavigator
                  novelId={nid}
                  selectedEntityId={effectiveSelectedEntityId}
                  onSelectEntity={setSelectedEntity}
                  bottomSlot={
                    <>
                      <WorldBuildPanel novelId={nid} />
                      <RelationshipSidebarPanel
                        novelId={nid}
                        selectedEntityId={effectiveSelectedEntityId}
                        selectedEntityName={effectiveSelectedEntityName}
                        onRequestNewRelationship={() => setRelCreateOpen(true)}
                        onOpenDraftReview={() => openDraftReview('relationships')}
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
                  <DraftReviewNavigator
                    novelId={nid}
                    kind={reviewKind}
                    onKindChange={handleReviewKindChange}
                    search={reviewSearch}
                    onSearchChange={setReviewSearch}
                    activeItemId={effectiveReviewHighlight}
                    onSelectItem={handleReviewSelect}
                  />
                  <div className="flex-1 min-w-0 overflow-hidden">
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
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </ArtifactStage>
          <NovelCopilotDrawer novelId={nid} onLocateTarget={handleLocateCopilotTarget} />
        </NovelShellLayout>
      </div>
    </AtlasShell>
  )
}
