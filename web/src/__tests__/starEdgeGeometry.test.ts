import { describe, expect, it } from 'vitest'
import { getParallelEdgeShift } from '@/components/world-model/relationships/starEdgeGeometry'

describe('getParallelEdgeShift', () => {
  it('keeps a single edge unshifted', () => {
    const shifted = getParallelEdgeShift(0, 0, 100, 0, 0, 1)
    expect(shifted).toEqual({ sourceX: 0, sourceY: 0, targetX: 100, targetY: 0 })
  })

  it('splits two parallel horizontal edges to opposite sides', () => {
    const a = getParallelEdgeShift(0, 0, 100, 0, 0, 2)
    const b = getParallelEdgeShift(0, 0, 100, 0, 1, 2)

    expect(a.sourceY).toBeLessThan(0)
    expect(b.sourceY).toBeGreaterThan(0)
    expect(Math.abs(a.sourceY)).toBe(Math.abs(b.sourceY))
    expect(a.sourceY).toBe(a.targetY)
    expect(b.sourceY).toBe(b.targetY)
  })

  it('defensively handles zero-length edges', () => {
    const shifted = getParallelEdgeShift(20, 20, 20, 20, 1, 3)
    expect(shifted).toEqual({ sourceX: 20, sourceY: 20, targetX: 20, targetY: 20 })
  })
})
