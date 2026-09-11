import { MarkerType, type Edge, type Node } from '@xyflow/react'
import { LABELS } from '@/constants/labels'
import type { GraphPositions, RelationshipGraphTopology } from './relationshipGraphGeometry'
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

/** Only node membership and unique connections influence geometry. */
export function getRelationshipTopologyKey(centerId: number, relationships: WorldRelationship[]): string {
  const adjacency = new Map<number, Set<number>>()
  for (const rel of relationships) {
    if (!adjacency.has(rel.source_id)) adjacency.set(rel.source_id, new Set())
    if (!adjacency.has(rel.target_id)) adjacency.set(rel.target_id, new Set())
    adjacency.get(rel.source_id)!.add(rel.target_id)
    adjacency.get(rel.target_id)!.add(rel.source_id)
  }
  const connected = new Set([centerId])
  const queue = [centerId]
  for (let index = 0; index < queue.length; index++) {
    for (const neighbor of adjacency.get(queue[index]) ?? []) {
      if (connected.has(neighbor)) continue
      connected.add(neighbor)
      queue.push(neighbor)
    }
  }
  const ids = [...connected].sort((a, b) => a - b)
  const pairs: [number, number][] = []
  for (const source of ids) {
    for (const target of adjacency.get(source) ?? []) {
      if (source < target) pairs.push([source, target])
    }
  }
  pairs.sort((a, b) => a[0] - b[0] || a[1] - b[1])
  return JSON.stringify({ ids, pairs } satisfies RelationshipGraphTopology)
}

export function buildGraph(
  centerId: number,
  relationships: WorldRelationship[],
  entityMap: Map<number, WorldEntity>,
  positions: GraphPositions,
  selectedRelId: number | null = null,
): { nodes: Node<StarNodeData>[]; edges: Edge[] } {
  const ids = [...positions.keys()]
  const rels = relationships.filter(r => positions.has(r.source_id) && positions.has(r.target_id)).sort((a, b) => a.id - b.id)
  const nodes: Node<StarNodeData>[] = ids.map(id => {
    const entity = entityMap.get(id)
    const position = positions.get(id)!
    return {
      id: String(id), type: 'star',
      position: { x: position.x - 72, y: position.y - 12 },
      data: {
        label: entity?.name ?? '?',
        entityTypeLabel: LABELS.ENTITY_TYPE_LABEL(entity?.entity_type ?? ''),
        isCenter: id === centerId,
        isDraft: entity?.status === 'draft',
      },
      ariaLabel: entity?.name,
      draggable: false,
    }
  })

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

    const source = positions.get(r.source_id)!
    const target = positions.get(r.target_id)!
    const angle = Math.atan2(target.y - source.y, target.x - source.x)
    const sourceHandle = angleToHandle(angle)
    const targetHandle = r.source_id === r.target_id ? 'top' : angleToHandle(angle + Math.PI)
    const selected = selectedRelId === r.id

    return {
      id: `rel-${r.id}`,
      source: String(r.source_id),
      target: String(r.target_id),
      sourceHandle: `${sourceHandle}-src`,
      targetHandle,
      type: 'star',
      label: r.label,
      ariaLabel: `${entityMap.get(r.source_id)?.name ?? r.source_id} → ${entityMap.get(r.target_id)?.name ?? r.target_id}: ${r.label}`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: selected ? 'hsl(var(--accent))' : 'hsl(var(--muted-foreground) / .5)' },
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
            ? 'hsl(var(--color-status-draft) / 0.45)'
            : 'hsl(var(--muted-foreground) / 0.44)',
        strokeWidth: selected ? 2 : 1.5,
        strokeLinecap: 'round',
        ...(r.status === 'draft' ? { strokeDasharray: '6 3' } : {}),
      },
      animated: false,
    }
  })

  return { nodes, edges }
}
