export interface RelationshipGraphTopology {
  ids: number[]
  pairs: [number, number][]
}

export type GraphPositions = Map<number, { x: number; y: number }>

/** Stable spring layout for the connected network around an entity. */
export function layoutRelationshipGraph({ ids, pairs: links }: RelationshipGraphTopology) {
  const points = ids.map((id, index) => ({
    id,
    x: index === 0 ? 0 : Math.cos(index * 2.39996) * Math.sqrt(index) * 130,
    y: index === 0 ? 0 : Math.sin(index * 2.39996) * Math.sqrt(index) * 105,
  }))
  const indices = new Map(ids.map((id, index) => [id, index]))
  const pairs = links.map(([source, target]) => [indices.get(source)!, indices.get(target)!])
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

