import { useMemo, useCallback, Fragment, type CSSProperties } from 'react'
import {
  ReactFlow,
  BaseEdge,
  Background,
  BackgroundVariant,
  EdgeLabelRenderer,
  Handle,
  Position,
  getBezierPath,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeMouseHandler,
  type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { cn } from '@/lib/utils'
import { LABELS } from '@/constants/labels'
import type { WorldRelationship, WorldEntity } from '@/types/api'
import { buildGraph, type StarNodeData } from './starGraphLayout'
import { getParallelEdgeShift } from './starEdgeGeometry'

const HANDLE_CLS = '!w-0 !h-0 !border-0 !bg-transparent'
const HANDLES = [
  { id: 'top', pos: Position.Top },
  { id: 'right', pos: Position.Right },
  { id: 'bottom', pos: Position.Bottom },
  { id: 'left', pos: Position.Left },
] as const

function StarNode({ data }: NodeProps<Node<StarNodeData>>) {
  const typeText = data.isDraft ? `${data.entityTypeLabel} · ${LABELS.STATUS_DRAFT}` : data.entityTypeLabel
  return (
    <div className={cn(
      'px-4 py-2 rounded-xl border select-none backdrop-blur-2xl transition-colors',
      data.isCenter
        ? 'border-accent border-2 font-semibold text-foreground bg-[hsl(var(--color-accent)/0.12)] shadow-[0_0_28px_hsl(var(--color-accent)/0.18)]'
        : 'border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.06)] hover:border-[var(--nw-glass-border-hover)] hover:bg-[hsl(var(--foreground)/0.09)] cursor-pointer text-foreground shadow-[0_10px_30px_rgba(0,0,0,0.35)]'
    )}>
      {HANDLES.map(({ id, pos }) => (
        <Fragment key={id}>
          <Handle id={id} type="target" position={pos} className={HANDLE_CLS} />
          <Handle id={`${id}-src`} type="source" position={pos} className={HANDLE_CLS} />
        </Fragment>
      ))}
      <div className="flex flex-col items-center gap-0.5">
        <div className={cn('font-mono leading-none drop-shadow-sm', data.isCenter ? 'text-[15px] font-semibold' : 'text-sm font-medium')}>
          {data.label}
        </div>
        <div className="flex items-center">
          <div
            className={cn(
              'rounded-full border px-2 py-0.5 text-[10px] leading-none backdrop-blur-xl',
              data.isDraft
                ? 'border-[hsl(var(--color-status-draft)/0.40)] bg-[hsl(var(--color-status-draft)/0.10)] text-[hsl(var(--color-status-draft))]'
                : data.isCenter
                  ? 'border-[hsl(var(--color-accent)/0.35)] bg-[hsl(var(--color-accent)/0.10)] text-[hsl(var(--color-accent))]'
                  : 'border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.05)] text-muted-foreground',
            )}
          >
            {typeText}
          </div>
        </div>
      </div>
    </div>
  )
}

const nodeTypes = { star: StarNode }

function StarEdge({
  id,
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
  const edgeIndex = typeof data?.edgeIndex === 'number' ? data.edgeIndex : 0
  const edgeCount = typeof data?.edgeCount === 'number' ? data.edgeCount : 1
  const shifted = getParallelEdgeShift(sourceX, sourceY, targetX, targetY, edgeIndex, edgeCount)
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: shifted.sourceX,
    sourceY: shifted.sourceY,
    targetX: shifted.targetX,
    targetY: shifted.targetY,
    sourcePosition,
    targetPosition,
  })

  const selected = Boolean(data?.selected)
  const isDraft = data?.status === 'draft'

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            // Follow XYFlow label positioning pattern.
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            className={cn(
              'pointer-events-none absolute max-w-[220px] truncate',
              'rounded-md px-2 py-0.5 text-[10px] backdrop-blur-xl border',
              selected
                ? 'border-accent bg-[hsl(var(--color-accent)/0.12)] text-foreground'
                : isDraft
                  ? 'border-[hsl(var(--color-status-draft)/0.45)] bg-[hsl(var(--color-status-draft)/0.10)] text-[hsl(var(--color-status-draft))]'
                  : 'border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.06)] text-[hsl(var(--foreground)/0.82)]',
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

export function StarGraph({ centerId, relationships, entities, onSelectEntity, onSelectEdge, selectedRelId, onClearSelection }: {
  centerId: number
  relationships: WorldRelationship[]
  entities: WorldEntity[]
  onSelectEntity: (id: number) => void
  onSelectEdge: (rel: WorldRelationship) => void
  selectedRelId?: number | null
  onClearSelection?: () => void
}) {
  const entityMap = useMemo(() => new Map(entities.map(e => [e.id, e])), [entities])

  const selectedRelIdValue = selectedRelId ?? null
  const { nodes, edges } = useMemo(
    () => buildGraph(centerId, relationships, entityMap, selectedRelIdValue),
    [centerId, relationships, entityMap, selectedRelIdValue],
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.id !== String(centerId)) onSelectEntity(Number(node.id))
  }, [centerId, onSelectEntity])

  const onEdgeClick: EdgeMouseHandler = useCallback((_: React.MouseEvent, edge: Edge) => {
    const rel = relationships.find(r => r.id === edge.data?.relId)
    if (rel) onSelectEdge(rel)
  }, [relationships, onSelectEdge])

  return (
    <div className="w-full h-full">
      <ReactFlow
        key={centerId}
        className="bg-transparent"
        colorMode="dark"
        style={{
          '--xy-background-color': 'transparent',
          // Defensive overrides: ensure no default XYFlow label/node surfaces render as opaque white
          // (we render custom glass chips for nodes/labels).
          '--xy-node-background-color': 'transparent',
          '--xy-edge-label-background-color': 'transparent',
          '--xy-edge-label-color': 'hsl(var(--foreground))',
        } as CSSProperties}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={() => onClearSelection?.()}
        proOptions={{ hideAttribution: true }}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        preventScrolling
        fitView
        fitViewOptions={{ padding: 0.12 }}
      >
        <Background variant={BackgroundVariant.Dots} color="hsl(var(--foreground) / 0.045)" gap={18} size={1} />
      </ReactFlow>
    </div>
  )
}
