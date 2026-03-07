export type ParallelEdgeShift = {
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
}

const DEFAULT_PARALLEL_EDGE_GAP = 10

/**
 * Shift overlapping edges along their perpendicular axis so each edge stays clickable.
 */
export function getParallelEdgeShift(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  edgeIndex: number,
  edgeCount: number,
  gap: number = DEFAULT_PARALLEL_EDGE_GAP,
): ParallelEdgeShift {
  if (edgeCount <= 1) {
    return { sourceX, sourceY, targetX, targetY }
  }

  const lane = edgeIndex - (edgeCount - 1) / 2
  if (lane === 0) {
    return { sourceX, sourceY, targetX, targetY }
  }

  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const length = Math.hypot(dx, dy)

  // Defensive fallback for degenerate edges (e.g. self loops), avoid NaN geometry.
  if (length === 0) {
    return { sourceX, sourceY, targetX, targetY }
  }

  const nx = -dy / length
  const ny = dx / length
  const shiftX = nx * lane * gap
  const shiftY = ny * lane * gap

  return {
    sourceX: sourceX + shiftX,
    sourceY: sourceY + shiftY,
    targetX: targetX + shiftX,
    targetY: targetY + shiftY,
  }
}
