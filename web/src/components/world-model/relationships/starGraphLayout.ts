import { MarkerType, type Edge, type Node } from '@xyflow/react'
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

/** Stable spring layout for the connected network around an entity. */
function layoutNeighborhood(ids: number[], relationships: WorldRelationship[]) {
  const points = ids.map((id, index) => ({
    id,
    x: index === 0 ? 0 : Math.cos(index * 2.39996) * Math.sqrt(index) * 130,
    y: index === 0 ? 0 : Math.sin(index * 2.39996) * Math.sqrt(index) * 105,
  }))
  const indices = new Map(ids.map((id, index) => [id, index]))
  // Multiple facts about one pair share a spring, so duplicates do not pull nodes together.
  const pairs = [...new Map(relationships.filter(r => r.source_id !== r.target_id).map(r => [
    [r.source_id, r.target_id].sort((a, b) => a - b).join(':'),
    [indices.get(r.source_id)!, indices.get(r.target_id)!],
  ])).values()]
  for (let iteration = 0; iteration < 180; iteration++) {
    const forces = points.map(() => ({ x: 0, y: 0 }))
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dx = points[i].x - points[j].x
        const dy = points[i].y - points[j].y
        const squaredDistance = Math.max(1, dx * dx + dy * dy)
        const push = 12000 / squaredDistance
        forces[i].x += dx * push; forces[j].x -= dx * push
        forces[i].y += dy * push; forces[j].y -= dy * push
      }
    }
    for (const [source, target] of pairs) {
      const dx = points[target].x - points[source].x
      const dy = points[target].y - points[source].y
      const pull = Math.hypot(dx, dy) / 650
      forces[source].x += dx * pull; forces[target].x -= dx * pull
      forces[source].y += dy * pull; forces[target].y -= dy * pull
    }
    const step = 10 * (1 - iteration / 180) + 0.1
    points.forEach((point, index) => {
      if (index === 0) return
      const force = forces[index]
      const length = Math.max(1, Math.hypot(force.x, force.y))
      point.x += force.x / length * Math.min(step, length)
      point.y += force.y / length * Math.min(step, length)
    })
  }
  // Label-aware spacing: shallow collisions are resolved without changing graph topology.
  for (let pass = 0; pass < 24; pass++) {
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const dx = points[j].x - points[i].x
      const dy = points[j].y - points[i].y
      if (Math.abs(dx) >= 170 || Math.abs(dy) >= 90) continue
      const shift = (90 - Math.abs(dy)) * (i === 0 ? 1 : 0.5)
      const sign = dy >= 0 ? 1 : -1
      points[j].y += shift * sign
      if (i !== 0) points[i].y -= shift * sign
    }
  }
  return new Map(points.map(point => [point.id, point]))
}

export function buildGraph(
  centerId: number,
  relationships: WorldRelationship[],
  entityMap: Map<number, WorldEntity>,
  selectedRelId: number | null = null,
): { nodes: Node<StarNodeData>[]; edges: Edge[] } {
  const adjacency = new Map<number, number[]>()
  relationships.forEach(rel => {
    adjacency.set(rel.source_id, [...(adjacency.get(rel.source_id) ?? []), rel.target_id])
    adjacency.set(rel.target_id, [...(adjacency.get(rel.target_id) ?? []), rel.source_id])
  })
  const connected = new Set([centerId])
  const queue = [centerId]
  for (let index = 0; index < queue.length; index++) {
    for (const neighbor of adjacency.get(queue[index]) ?? []) {
      if (connected.has(neighbor)) continue
      connected.add(neighbor)
      queue.push(neighbor)
    }
  }
  // Focus changes highlight, not the map's shape. Separate networks stay out of view.
  const ids = [...connected].sort((a, b) => a - b)
  const rels = relationships.filter(r => connected.has(r.source_id) && connected.has(r.target_id)).sort((a, b) => a.id - b.id)
  const positions = layoutNeighborhood(ids, rels)
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
