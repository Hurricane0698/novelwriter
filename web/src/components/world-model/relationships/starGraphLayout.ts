import type { Edge, Node } from '@xyflow/react'
import { LABELS } from '@/constants/labels'
import type { WorldEntity, WorldRelationship } from '@/types/api'

export type StarNodeData = {
  label: string
  entityTypeLabel: string
  isCenter: boolean
  isDraft: boolean
}

/** Map angle (radians, 0 = right) to closest cardinal handle id */
function angleToHandle(angle: number): string {
  const a = ((angle % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  if (a < Math.PI / 4 || a >= 7 * Math.PI / 4) return 'right'
  if (a < 3 * Math.PI / 4) return 'bottom'
  if (a < 5 * Math.PI / 4) return 'left'
  return 'top'
}

/** Estimated node width in px (label + type badge + padding) */
const EST_NODE_W = 160
/** Minimum arc gap between adjacent peer nodes */
const MIN_ARC_GAP = 40
/** Baseline radius for small graphs */
const BASE_RADIUS = 200

export function buildGraph(
  centerId: number,
  relationships: WorldRelationship[],
  entityMap: Map<number, WorldEntity>,
  selectedRelId: number | null = null,
): { nodes: Node<StarNodeData>[]; edges: Edge[] } {
  const rels = relationships.filter(r => r.source_id === centerId || r.target_id === centerId)
  const peers = [...new Set(rels.map(r => r.source_id === centerId ? r.target_id : r.source_id))]
    .filter((peerId) => peerId !== centerId)

  const centerEntity = entityMap.get(centerId)
  const N = peers.length

  // Dynamic radius: ensure adjacent nodes don't overlap
  // circumference = 2πr, arc per peer = 2πr/N, need arc >= EST_NODE_W + MIN_ARC_GAP
  const minRadius = N > 0 ? (N * (EST_NODE_W + MIN_ARC_GAP)) / (2 * Math.PI) : BASE_RADIUS
  const radius = Math.max(BASE_RADIUS, minRadius)

  // Canvas sized to fit radius + node padding
  const padding = EST_NODE_W
  const canvasW = 2 * radius + 2 * padding
  const canvasH = 2 * radius + 2 * padding
  const cx = canvasW / 2
  const cy = canvasH / 2

  const peerAngles = new Map<number, number>()

  const nodes: Node<StarNodeData>[] = [
    {
      id: String(centerId),
      type: 'star',
      position: { x: cx - 60, y: cy - 20 },
      data: {
        label: centerEntity?.name ?? '?',
        entityTypeLabel: LABELS.ENTITY_TYPE_LABEL(centerEntity?.entity_type ?? ''),
        isCenter: true,
        isDraft: centerEntity?.status === 'draft',
      },
      draggable: false,
    },
    ...peers.map((pid, i) => {
      const angle = (2 * Math.PI * i) / N - Math.PI / 2
      peerAngles.set(pid, angle)
      const e = entityMap.get(pid)
      return {
        id: String(pid),
        type: 'star' as const,
        position: { x: cx + radius * Math.cos(angle) - 50, y: cy + radius * Math.sin(angle) - 16 },
        data: {
          label: e?.name ?? '?',
          entityTypeLabel: LABELS.ENTITY_TYPE_LABEL(e?.entity_type ?? ''),
          isCenter: false,
          isDraft: e?.status === 'draft',
        },
        draggable: false,
      }
    }),
  ]

  const groupTotals = new Map<string, number>()
  rels.forEach((r) => {
    const key = `${Math.min(r.source_id, r.target_id)}-${Math.max(r.source_id, r.target_id)}`
    groupTotals.set(key, (groupTotals.get(key) ?? 0) + 1)
  })
  const groupIndex = new Map<string, number>()

  const edges: Edge[] = rels.map(r => {
    const groupKey = `${Math.min(r.source_id, r.target_id)}-${Math.max(r.source_id, r.target_id)}`
    const edgeIndex = groupIndex.get(groupKey) ?? 0
    groupIndex.set(groupKey, edgeIndex + 1)

    const peerId = r.source_id === centerId ? r.target_id : r.source_id
    const peerAngle = peerAngles.get(peerId) ?? 0
    const isSourceCenter = r.source_id === centerId
    const centerHandle = angleToHandle(peerAngle)
    const peerHandle = angleToHandle(peerAngle + Math.PI)
    const selected = selectedRelId === r.id

    return {
      id: `rel-${r.id}`,
      source: String(r.source_id),
      target: String(r.target_id),
      sourceHandle: isSourceCenter ? `${centerHandle}-src` : `${peerHandle}-src`,
      targetHandle: isSourceCenter ? peerHandle : centerHandle,
      type: 'star',
      label: r.label,
      data: {
        relId: r.id,
        status: r.status,
        selected,
        edgeIndex,
        edgeCount: groupTotals.get(groupKey) ?? 1,
      },
      style: {
        stroke: selected
          ? 'hsl(var(--color-accent) / 0.92)'
          : r.status === 'draft'
            ? 'hsl(var(--color-status-draft) / 0.70)'
            : 'hsl(var(--color-accent) / 0.45)',
        strokeWidth: selected ? 2.75 : r.status === 'draft' ? 1.9 : 1.55,
        strokeLinecap: 'round',
        ...(r.status === 'draft' ? { strokeDasharray: '6 3' } : {}),
      },
      animated: selected,
    }
  })

  return { nodes, edges }
}
