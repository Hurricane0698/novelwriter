import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type OnConnect,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { cn } from '@/lib/utils'
import { GlassSurface } from '@/components/ui/glass-surface'
import type { Visibility } from '@/types/api'

interface GraphNode {
  id: string
  label: string
  entity_id: number | null
  position: { x: number; y: number }
  visibility: Visibility
}

interface GraphEdge {
  from: string
  to: string
  label: string
  visibility: Visibility
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

function PillNode({
  data,
  selected,
}: NodeProps<Node<{ label: string; onLabelChange: (v: string) => void }>>) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(data.label)

  if (editing) {
    return (
      <GlassSurface
        variant="floating"
        className="px-3 py-1.5 rounded-full border-[var(--nw-glass-border-hover)] shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
      >
        <Handle type="target" position={Position.Left} className="!w-2 !h-2" />
        <input
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={() => { setEditing(false); if (draft !== data.label) data.onLabelChange(draft) }}
          onKeyDown={e => { if (e.key === 'Enter') { setEditing(false); data.onLabelChange(draft) } if (e.key === 'Escape') { setEditing(false); setDraft(data.label) } }}
          className="bg-transparent text-sm outline-none w-20 text-center text-foreground placeholder:text-muted-foreground/70"
        />
        <Handle type="source" position={Position.Right} className="!w-2 !h-2" />
      </GlassSurface>
    )
  }

  return (
    <GlassSurface
      variant="floating"
      hoverable
      className={cn(
        'px-3 py-1.5 rounded-full shadow-[0_10px_30px_rgba(0,0,0,0.35)] text-sm cursor-pointer',
        selected && 'border-accent shadow-[0_0_28px_hsl(var(--color-accent)/0.22)]',
      )}
      onDoubleClick={() => { setDraft(data.label); setEditing(true) }}
    >
      <Handle type="target" position={Position.Left} className="!w-2 !h-2" />
      {data.label || '\u00A0'}
      <Handle type="source" position={Position.Right} className="!w-2 !h-2" />
    </GlassSurface>
  )
}

const nodeTypes = { pill: PillNode }

let _nodeCounter = 0
const newId = () => `gnode_${Date.now()}_${++_nodeCounter}`

function flowToGraphData(
  flowNodes: Node[],
  flowEdges: Edge[],
  meta: {
    nodeById: Map<string, GraphNode>
    edgeByKey: Map<string, GraphEdge>
  },
): GraphData {
  const nodes: GraphNode[] = flowNodes.map((n) => {
    const base = meta.nodeById.get(n.id)
    const label = typeof (n.data as { label?: unknown } | undefined)?.label === 'string'
      ? (n.data as { label: string }).label
      : (base?.label ?? '')

    return {
      id: n.id,
      label,
      entity_id: base?.entity_id ?? null,
      position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
      visibility: base?.visibility ?? 'active',
    }
  })

  const edges: GraphEdge[] = flowEdges
    .filter((e) => typeof e.source === 'string' && typeof e.target === 'string')
    .map((e) => {
      const key = `${e.source}-${e.target}`
      const base = meta.edgeByKey.get(key)
      const label = typeof e.label === 'string' ? e.label : (base?.label ?? '')
      return {
        from: e.source,
        to: e.target,
        label,
        visibility: base?.visibility ?? 'active',
      }
    })

  return { nodes, edges }
}

export function GraphEditor({ data, onUpdate }: {
  data: GraphData
  onUpdate: (data: GraphData) => void
}) {
  const graphNodes = useMemo(() => data.nodes ?? [], [data.nodes])
  const graphEdges = useMemo(() => data.edges ?? [], [data.edges])

  const onLabelChangeRef = useRef<(id: string, label: string) => void>(() => {})

  const toFlowNodes = useCallback((gn: GraphNode[]): Node[] =>
    gn.map(n => ({
      id: n.id,
      type: 'pill',
      position: n.position,
      data: { label: n.label, onLabelChange: (v: string) => onLabelChangeRef.current(n.id, v) },
    })), [])

  const toFlowEdges = (ge: GraphEdge[]): Edge[] =>
    ge.map(e => ({ id: `${e.from}-${e.to}`, source: e.from, target: e.to, label: e.label }))

  const meta = useMemo(() => {
    const nodeById = new Map<string, GraphNode>()
    for (const n of graphNodes) nodeById.set(n.id, n)
    const edgeByKey = new Map<string, GraphEdge>()
    for (const e of graphEdges) edgeByKey.set(`${e.from}-${e.to}`, e)
    return { nodeById, edgeByKey }
  }, [graphEdges, graphNodes])

  const [nodes, setNodes, onNodesChange] = useNodesState(toFlowNodes(graphNodes))
  const [edges, setEdges, onEdgesChange] = useEdgesState(toFlowEdges(graphEdges))

  const rfRef = useRef<ReactFlowInstance | null>(null)
  const suppressedEdgeIds = useRef<Set<string> | null>(null)

  const handleLabelChange = useCallback((id: string, label: string) => {
    const nextNodes = nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n))
    setNodes(nextNodes)
    onUpdate(flowToGraphData(nextNodes, edges, meta))
  }, [edges, meta, nodes, onUpdate, setNodes])

  // Ref indirection so node data callbacks always see the latest handler.
  // Use layout effect so it's updated before the browser paints.
  useLayoutEffect(() => {
    onLabelChangeRef.current = handleLabelChange
  }, [handleLabelChange])

  useEffect(() => {
    setNodes(toFlowNodes(graphNodes))
  }, [graphNodes, setNodes, toFlowNodes])

  useEffect(() => {
    setEdges(toFlowEdges(graphEdges))
  }, [graphEdges, setEdges])

  const onConnect: OnConnect = useCallback((params) => {
    const nextEdges = addEdge({ ...params, label: '' }, edges)
    setEdges(nextEdges)
    onUpdate(flowToGraphData(nodes, nextEdges, meta))
  }, [edges, meta, nodes, onUpdate, setEdges])

  const onNodeDragStop = useCallback((_: unknown, node: Node) => {
    const next = nodes.map((n) => (n.id === node.id ? { ...n, position: node.position } : n))
    onUpdate(flowToGraphData(next, edges, meta))
  }, [edges, meta, nodes, onUpdate])

  const onNodesDelete = useCallback((deleted: Node[]) => {
    const deletedIds = new Set(deleted.map((n) => n.id))
    const nextNodes = nodes.filter((n) => !deletedIds.has(n.id))
    const edgesDeletedByNode = edges.filter((e) => deletedIds.has(e.source) || deletedIds.has(e.target))
    suppressedEdgeIds.current = new Set(edgesDeletedByNode.map((e) => e.id))
    const nextEdges = edges.filter((e) => !deletedIds.has(e.source) && !deletedIds.has(e.target))
    onUpdate(flowToGraphData(nextNodes, nextEdges, meta))
  }, [edges, meta, nodes, onUpdate])

  const onEdgesDelete = useCallback((deleted: Edge[]) => {
    const suppressed = suppressedEdgeIds.current
    if (suppressed && deleted.every((e) => suppressed.has(e.id))) {
      deleted.forEach((e) => suppressed.delete(e.id))
      if (suppressed.size === 0) suppressedEdgeIds.current = null
      return
    }
    suppressedEdgeIds.current = null
    const deletedIds = new Set(deleted.map((e) => e.id))
    const nextEdges = edges.filter((e) => !deletedIds.has(e.id))
    onUpdate(flowToGraphData(nodes, nextEdges, meta))
  }, [edges, meta, nodes, onUpdate])

  const addNode = () => {
    const id = newId()
    const newNode: GraphNode = { id, label: '', entity_id: null, position: { x: 100 + Math.random() * 200, y: 100 + Math.random() * 200 }, visibility: 'active' }
    const nextNodes = [...nodes, { id, type: 'pill', position: newNode.position, data: { label: '', onLabelChange: (v: string) => onLabelChangeRef.current(id, v) } }]
    setNodes(nextNodes)
    onUpdate(flowToGraphData(nextNodes, edges, {
      nodeById: new Map(meta.nodeById).set(id, newNode),
      edgeByKey: meta.edgeByKey,
    }))
    requestAnimationFrame(() => rfRef.current?.fitView({ padding: 0.12, duration: 250 }))
  }

  return (
    <GlassSurface
      variant="container"
      className={cn('h-[420px] rounded-2xl overflow-hidden relative')}
    >
      <ReactFlow
        className="bg-transparent"
        colorMode="dark"
        style={{
          '--xy-background-color': 'transparent',
          '--xy-background-pattern-color': 'hsl(var(--foreground) / 0.045)',
          '--xy-edge-stroke': 'hsl(var(--foreground) / 0.30)',
          '--xy-edge-stroke-selected': 'hsl(var(--color-accent) / 0.65)',
          '--xy-connectionline-stroke': 'hsl(var(--foreground) / 0.35)',
          '--xy-controls-button-background-color': 'hsl(var(--background) / 0.72)',
          '--xy-controls-button-background-color-hover': 'hsl(var(--background) / 0.85)',
          '--xy-controls-button-border-color': 'var(--nw-glass-border)',
          '--xy-controls-button-color': 'hsl(var(--foreground) / 0.92)',
          '--xy-controls-button-color-hover': 'hsl(var(--foreground))',
          '--xy-controls-box-shadow': '0 10px 30px rgba(0,0,0,0.35)',
          '--xy-edge-label-background-color': 'hsl(var(--background) / 0.65)',
          '--xy-edge-label-color': 'hsl(var(--foreground) / 0.92)',
          // Defensive: ensure no default XYFlow nodes render as opaque white.
          '--xy-node-background-color': 'transparent',
        } as CSSProperties}
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        nodeTypes={nodeTypes}
        deleteKeyCode={['Backspace', 'Delete']}
        zoomOnDoubleClick={false}
        preventScrolling
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        proOptions={{ hideAttribution: true }}
        onInit={(instance) => { rfRef.current = instance }}
        fitView
        fitViewOptions={{ padding: 0.12 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
        <Controls />
      </ReactFlow>
      <GlassSurface
        asChild
        variant="floating"
        hoverable
        className="absolute top-2 right-2 z-10 w-8 h-8 rounded-full flex items-center justify-center text-sm shadow-none"
      >
        <button type="button" onClick={addNode}>
          +
        </button>
      </GlassSurface>
    </GlassSurface>
  )
}
