import { useMemo, useCallback, useEffect, useState, useRef, Fragment, type CSSProperties } from 'react'
import {
  ReactFlow,
  BaseEdge,
  Background,
  BackgroundVariant,
  EdgeLabelRenderer,
  Handle,
  Position,
  getBezierPath,
  useReactFlow,
  useStore,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeMouseHandler,
  type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Maximize, Minus, Plus } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { LABELS } from '@/constants/labels'
import type { WorldRelationship, WorldEntity } from '@/types/api'
import { buildGraph, type StarNodeData } from './starGraphLayout'
import { useRelationshipGraphLayout } from './useRelationshipGraphLayout'
import { getParallelEdgeShift } from './starEdgeGeometry'

const HANDLE_CLS = '!w-0 !h-0 !border-0 !bg-transparent'
const HANDLES = [
  { id: 'top', pos: Position.Top },
  { id: 'right', pos: Position.Right },
  { id: 'bottom', pos: Position.Bottom },
  { id: 'left', pos: Position.Left },
] as const

function StarNode({ data }: NodeProps<Node<StarNodeData>>) {
  const zoom = useStore(state => state.transform[2])
  const typeText = data.isDraft ? `${data.entityTypeLabel} · ${LABELS.STATUS_DRAFT}` : data.entityTypeLabel
  return (
    <div className="group relative flex w-[144px] select-none flex-col items-center pt-1" style={{ height: Math.max(64, 52 / zoom) }} title={data.label}>
      {HANDLES.map(({ id, pos }) => (
        <Fragment key={id}>
          <Handle id={id} type="target" position={pos} className={HANDLE_CLS} style={{ left: '50%', top: 12 }} />
          <Handle id={`${id}-src`} type="source" position={pos} className={HANDLE_CLS} style={{ left: '50%', top: 12 }} />
        </Fragment>
      ))}
      <span className={cn('mb-2 block shrink-0 rounded-full transition-shadow', data.isCenter
        ? 'h-4 w-4 bg-accent ring-4 ring-accent/10'
        : 'mt-1 h-2 w-2 bg-accent/60 ring-4 ring-background group-hover:ring-accent/15')} />
      <span className={cn('max-w-full shrink-0 truncate bg-background/90 px-1 text-sm leading-5', data.isCenter ? 'font-semibold text-accent' : 'font-medium text-foreground')} style={{ fontSize: Math.max(14, 12 / zoom), lineHeight: `${Math.max(20, 18 / zoom)}px` }}>{data.label}</span>
      <span className="shrink-0 bg-background/90 px-1 text-[10px] leading-4 text-muted-foreground" style={{ fontSize: Math.max(10, 10 / zoom), lineHeight: `${Math.max(16, 14 / zoom)}px` }}>{typeText}</span>
    </div>
  )
}

const nodeTypes = { star: StarNode }

function StarEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
}: EdgeProps) {
  const zoom = useStore(state => state.transform[2])
  const edgeIndex = typeof data?.edgeIndex === 'number' ? data.edgeIndex : 0
  const edgeCount = typeof data?.edgeCount === 'number' ? data.edgeCount : 1
  const shifted = getParallelEdgeShift(sourceX, sourceY, targetX, targetY, edgeIndex, edgeCount)
  const loopRadius = 60 + edgeIndex * 18
  const [edgePath, labelX, labelY] = source === target
    ? [`M ${sourceX},${sourceY} C ${sourceX - loopRadius},${sourceY - loopRadius * 1.6} ${sourceX + loopRadius},${sourceY - loopRadius * 1.6} ${sourceX},${sourceY}`, sourceX, sourceY - loopRadius] as const
    : getBezierPath({
    sourceX: shifted.sourceX,
    sourceY: shifted.sourceY,
    targetX: shifted.targetX,
    targetY: shifted.targetY,
    sourcePosition,
    targetPosition,
  })

  const selected = Boolean(data?.selected)

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {label && (selected || data?.hovered) ? (
        <EdgeLabelRenderer>
          <div
            // Follow XYFlow label positioning pattern.
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, fontSize: Math.max(12, 11 / zoom) }}
            className={cn(
              'pointer-events-none absolute max-w-[220px] truncate bg-background/95 px-2 py-1 text-xs',
              selected ? 'font-medium text-accent' : 'text-foreground',
            )}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}

const edgeTypes = { star: StarEdge }

function FitGraphToStage({ layoutKey }: { layoutKey: string }) {
  // This read-only graph does not write measured dimensions back to its node props.
  const initialized = useStore(state => state.nodeLookup.size > 0 &&
    [...state.nodeLookup.values()].every(node => node.measured.width && node.measured.height))
  const { fitView } = useReactFlow()
  const width = useStore(state => state.width)
  const height = useStore(state => state.height)
  const fittedKey = useRef<string | null>(null)
  useEffect(() => {
    if (!initialized || !width || !height || fittedKey.current === layoutKey) return
    fittedKey.current = layoutKey
    void fitView({ padding: 0.12, maxZoom: 1.15 })
  }, [initialized, layoutKey, width, height, fitView])
  return null
}

function GraphControls() {
  const { fitView, zoomIn, zoomOut } = useReactFlow()
  const { t } = useUiLocale()
  return <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1 border border-border/60 bg-background/95 p-1">
    {[{ label: t('worldModel.graph.zoomOut'), icon: Minus, action: () => zoomOut() },
      { label: t('worldModel.graph.zoomIn'), icon: Plus, action: () => zoomIn() },
      { label: t('worldModel.graph.fit'), icon: Maximize, action: () => fitView({ padding: .12, maxZoom: 1.15 }) }].map(({ label, icon: Icon, action }) =>
      <button key={label} type="button" aria-label={label} title={label} onClick={() => void action()} className="rounded p-2 text-muted-foreground hover:bg-foreground/5 hover:text-foreground"><Icon size={14} /></button>)}
  </div>
}

export function StarGraph({ topologyKey, centerId, relationships, entities, onSelectEntity, onSelectEdge, selectedRelId, onClearSelection }: {
  topologyKey: string
  centerId: number
  relationships: WorldRelationship[]
  entities: WorldEntity[]
  onSelectEntity: (id: number) => void
  onSelectEdge: (rel: WorldRelationship) => void
  selectedRelId?: number | null
  onClearSelection?: () => void
}) {
  const { theme } = useTheme()
  const { t } = useUiLocale()
  const [hoveredRelId, setHoveredRelId] = useState<number | null>(null)
  const entityMap = useMemo(() => new Map(entities.map(e => [e.id, e])), [entities])

  const { positions, failed, retry } = useRelationshipGraphLayout(topologyKey)
  const selectedRelIdValue = selectedRelId ?? null
  const { nodes, edges } = useMemo(
    () => positions ? buildGraph(centerId, relationships, entityMap, positions, selectedRelIdValue) : { nodes: [], edges: [] },
    [centerId, relationships, entityMap, positions, selectedRelIdValue],
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.id !== String(centerId)) onSelectEntity(Number(node.id))
  }, [centerId, onSelectEntity])

  const onEdgeClick: EdgeMouseHandler = useCallback((_: React.MouseEvent, edge: Edge) => {
    const rel = relationships.find(r => r.id === edge.data?.relId)
    if (rel) onSelectEdge(rel)
  }, [relationships, onSelectEdge])

  return (
    <div className="relative w-full h-full" aria-busy={!positions && !failed}>
      {!positions && <div className="absolute inset-0 z-10 flex items-center justify-center gap-3 bg-background text-sm text-muted-foreground" role="status">
        {t(failed ? 'worldModel.graph.layoutFailed' : 'worldModel.graph.layoutLoading')}
        {failed && <button type="button" onClick={retry} className="text-accent underline">{t('worldModel.graph.retry')}</button>}
      </div>}
      <ReactFlow
        className="bg-transparent"
        colorMode={theme}
        style={{
          '--xy-background-color': 'transparent',
          '--xy-node-background-color': 'transparent',
          '--xy-edge-label-background-color': 'transparent',
          '--xy-edge-label-color': 'hsl(var(--foreground))',
        } as CSSProperties}
        nodes={nodes}
        edges={edges.map(edge => ({ ...edge, data: { ...edge.data, hovered: edge.data?.relId === hoveredRelId } }))}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onEdgeMouseEnter={(_, edge: Edge) => setHoveredRelId(Number(edge.data?.relId))}
        onEdgeMouseLeave={() => setHoveredRelId(null)}
        onPaneClick={() => onClearSelection?.()}
        proOptions={{ hideAttribution: true }}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        preventScrolling
      >
        {positions && <FitGraphToStage layoutKey={topologyKey} />}
        <GraphControls />
        <Background variant={BackgroundVariant.Dots} color="hsl(var(--foreground) / 0.065)" gap={24} size={1} />
        <div className="pointer-events-none absolute left-5 top-4 z-10 text-[11px] text-muted-foreground">{t('worldModel.graph.hint')}</div>
      </ReactFlow>
    </div>
  )
}
