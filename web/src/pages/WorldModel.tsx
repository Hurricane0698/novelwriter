// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { GlassSurface } from '@/components/ui/glass-surface'
import { EntitySidebar } from '@/components/world-model/shared/EntitySidebar'
import { EntityDetail } from '@/components/world-model/entities/EntityDetail'
import { SystemsTab } from '@/components/world-model/systems/SystemsTab'
import { RelationshipsTab } from '@/components/world-model/relationships/RelationshipsTab'
import { WorldModelShell } from '@/components/world-model/WorldModelShell'
import { DraftReviewTab } from '@/components/world-model/shared/DraftReviewTab'
import { DraftReviewPreview, type DraftReviewKind } from '@/components/world-model/shared/DraftReviewPreview'
import { DraftReviewSidebar } from '@/components/world-model/shared/DraftReviewSidebar'
import { RelationshipSidebarSection } from '@/components/world-model/relationships/RelationshipSidebarSection'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { LABELS } from '@/constants/labels'

export function WorldModel() {
  const { novelId } = useParams<{ novelId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const nid = Number(novelId)
  const invalidNovelId = Number.isNaN(nid)
  // Capture returnTo on mount, then strip it from URL so it doesn't persist in history
  const [returnTo] = useState(() => searchParams.get('returnTo'))
  useEffect(() => {
    if (!searchParams.has('returnTo')) return
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      p.delete('returnTo')
      return p
    }, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [reviewSearch, setReviewSearch] = useState('')
  const [reviewHighlight, setReviewHighlight] = useState<number | null>(null)
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleReviewSelect = useCallback((_kind: DraftReviewKind, id: number) => {
    setReviewHighlight(id)
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    highlightTimerRef.current = setTimeout(() => setReviewHighlight(null), 2500)
  }, [])
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null)
  const [relCreateOpen, setRelCreateOpen] = useState(false)
  const { data: entities = [] } = useWorldEntities(nid)
  const selectedStillExists =
    selectedEntityId !== null && entities.some((entity) => entity.id === selectedEntityId)
  const effectiveSelectedEntityId =
    selectedEntityId === null ? null : selectedStillExists ? selectedEntityId : (entities[0]?.id ?? null)

  const tab = (() => {
    const value = searchParams.get('tab')
    if (value === 'entities' || value === 'relationships' || value === 'review' || value === 'systems') return value
    return 'systems'
  })()

  const reviewKind: DraftReviewKind = (() => {
    const value = searchParams.get('kind')
    if (value === 'entities' || value === 'relationships' || value === 'systems') return value
    return 'entities'
  })()

  if (invalidNovelId) return <div className="p-4 text-muted-foreground">Novel not found</div>

  const handleTabChange = (next: string) => {
    if (next !== 'relationships') setRelCreateOpen(false)
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      if (next === 'systems') p.delete('tab')
      else p.set('tab', next)
      return p
    }, { replace: true })
  }

  const openDraftReview = (kind?: DraftReviewKind) => {
    setReviewSearch('')
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      p.set('tab', 'review')
      p.set('kind', kind ?? p.get('kind') ?? 'entities')
      return p
    }, { replace: true })
  }

  const handleReviewKindChange = (kind: DraftReviewKind) => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      p.set('tab', 'review')
      p.set('kind', kind)
      return p
    }, { replace: true })
  }

  return (
    <WorldModelShell>
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <GlassSurface
          variant="floating"
          bordered={false}
          className="shrink-0 border-b px-6 py-3 flex items-center justify-end gap-2 shadow-none"
        >
          {returnTo && (
            <Button variant="outline" size="sm" onClick={() => navigate(returnTo)}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回续写结果
            </Button>
          )}
          <Button asChild variant="outline" size="sm">
            <Link to={`/novel/${nid}`}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回作品
            </Link>
          </Button>
        </GlassSurface>
        <Tabs value={tab} onValueChange={handleTabChange} className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-6">
            <TabsList className="bg-transparent h-auto p-0 gap-4">
              <TabsTrigger value="systems" className="rounded-none border-b-2 border-transparent text-muted-foreground data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 pb-2" data-testid="tab-systems">
                {LABELS.TAB_SYSTEMS}
              </TabsTrigger>
              <TabsTrigger value="entities" className="rounded-none border-b-2 border-transparent text-muted-foreground data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 pb-2" data-testid="tab-entities">
                {LABELS.TAB_ENTITIES}
              </TabsTrigger>
              <TabsTrigger value="relationships" className="rounded-none border-b-2 border-transparent text-muted-foreground data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 pb-2" data-testid="tab-relationships">
                {LABELS.TAB_RELATIONSHIPS}
              </TabsTrigger>
              {tab === 'review' ? (
                <TabsTrigger
                  value="review"
                  className="rounded-none border-b-2 border-transparent text-muted-foreground data-[state=active]:border-accent data-[state=active]:text-foreground data-[state=active]:bg-transparent px-1 pb-2"
                  data-testid="tab-review-indicator"
                >
                  草稿审核
                </TabsTrigger>
              ) : null}
            </TabsList>
          </div>

          <TabsContent value="systems" className="flex-1 min-h-0 mt-0 overflow-hidden">
            <SystemsTab novelId={nid} onOpenDraftReview={openDraftReview} />
          </TabsContent>

          <TabsContent value="entities" className="flex-1 min-h-0 flex mt-0 overflow-hidden">
            <EntitySidebar
              novelId={nid}
              selectedEntityId={effectiveSelectedEntityId}
              onSelectEntity={setSelectedEntityId}
              bottomSlot={<DraftReviewPreview novelId={nid} onOpen={openDraftReview} />}
            />
            <EntityDetail novelId={nid} entityId={effectiveSelectedEntityId} onDeleted={() => setSelectedEntityId(null)} />
          </TabsContent>

          <TabsContent value="relationships" className="flex-1 min-h-0 flex mt-0 overflow-hidden">
            <EntitySidebar
              novelId={nid}
              selectedEntityId={effectiveSelectedEntityId}
              onSelectEntity={setSelectedEntityId}
              bottomSlot={
                <>
                  <RelationshipSidebarSection
                    novelId={nid}
                    selectedEntityId={effectiveSelectedEntityId}
                    onRequestNewRelationship={() => setRelCreateOpen(true)}
                    onOpenDraftReview={() => openDraftReview('relationships')}
                  />
                  <DraftReviewPreview novelId={nid} onOpen={openDraftReview} />
                </>
              }
            />
            <RelationshipsTab
              novelId={nid}
              selectedEntityId={effectiveSelectedEntityId}
              onSelectEntity={setSelectedEntityId}
              creating={relCreateOpen}
              onCreatingChange={setRelCreateOpen}
            />
          </TabsContent>

          <TabsContent value="review" className="flex-1 min-h-0 mt-0 overflow-hidden">
            <div className="flex h-full min-h-0 overflow-hidden">
              <DraftReviewSidebar
                novelId={nid}
                kind={reviewKind}
                onKindChange={handleReviewKindChange}
                search={reviewSearch}
                onSearchChange={setReviewSearch}
                activeItemId={reviewHighlight}
                onSelectItem={handleReviewSelect}
              />
              <div className="flex-1 min-w-0 overflow-hidden">
                <DraftReviewTab
                  novelId={nid}
                  kind={reviewKind}
                  onKindChange={handleReviewKindChange}
                  search={reviewSearch}
                  showKindSelector={false}
                  highlightId={reviewHighlight}
                  onOpenEntity={(id) => {
                    setSelectedEntityId(id)
                    handleTabChange('entities')
                  }}
                  onOpenRelationships={(id) => {
                    setSelectedEntityId(id)
                    handleTabChange('relationships')
                  }}
                />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </WorldModelShell>
  )
}
