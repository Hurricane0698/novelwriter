import { describe, it, expect } from 'vitest'
import { buildGraph } from '@/components/world-model/relationships/starGraphLayout'
import type { WorldRelationship, WorldEntity } from '@/types/api'

const entity = (id: number, name: string): WorldEntity => ({
  id, name, entity_type: 'Character', novel_id: 1, status: 'confirmed',
  description: '', aliases: [], attributes: [],
})

const rel = (id: number, src: number, tgt: number, label = 'rel'): WorldRelationship => ({
  id, source_id: src, target_id: tgt, label, novel_id: 1,
  visibility: 'active', status: 'draft', description: '',
})

describe('buildGraph', () => {
  it('deduplicates peers with multiple edges to same entity', () => {
    const entities = new Map([[1, entity(1, 'A')], [2, entity(2, 'B')]])
    const rels = [rel(10, 1, 2, '师徒'), rel(11, 1, 2, '仇敌')]
    const { nodes, edges } = buildGraph(1, rels, entities)
    expect(nodes).toHaveLength(2) // center + 1 peer
    expect(edges).toHaveLength(2) // 2 edges
  })

  it('deduplicates bidirectional edges (A→B + B→A)', () => {
    const entities = new Map([[1, entity(1, 'A')], [2, entity(2, 'B')]])
    const rels = [rel(10, 1, 2), rel(11, 2, 1)]
    const { nodes } = buildGraph(1, rels, entities)
    expect(nodes).toHaveLength(2)
    const ids = nodes.map(n => n.id)
    expect(new Set(ids).size).toBe(2)
  })

  it('defensively handles self-referencing relationship without duplicate node IDs', () => {
    const entities = new Map([[1, entity(1, 'A')]])
    const rels = [rel(10, 1, 1, '自引用')]
    const { nodes, edges } = buildGraph(1, rels, entities)
    expect(edges).toHaveLength(1)
    const ids = nodes.map(n => n.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('handles entity with zero relationships', () => {
    const entities = new Map([[1, entity(1, 'A')]])
    const { nodes, edges } = buildGraph(1, [], entities)
    expect(nodes).toHaveLength(1) // center only
    expect(edges).toHaveLength(0)
  })

  it('handles many peers without duplicate node IDs', () => {
    const entries: [number, WorldEntity][] = [[1, entity(1, 'Center')]]
    const rels: WorldRelationship[] = []
    for (let i = 2; i <= 22; i++) {
      entries.push([i, entity(i, `E${i}`)])
      rels.push(rel(i * 10, 1, i))
    }
    const entities = new Map(entries)
    const { nodes } = buildGraph(1, rels, entities)
    const ids = nodes.map(n => n.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('expands radius when peer count is large to avoid overlap', () => {
    // With 20 peers the layout should be larger than with 3 peers
    const makeGraph = (peerCount: number) => {
      const entries: [number, WorldEntity][] = [[1, entity(1, 'Center')]]
      const rels: WorldRelationship[] = []
      for (let i = 2; i <= peerCount + 1; i++) {
        entries.push([i, entity(i, `E${i}`)])
        rels.push(rel(i * 10, 1, i))
      }
      return buildGraph(1, rels, new Map(entries))
    }
    const small = makeGraph(3)
    const large = makeGraph(20)
    // Bounding box of large graph should be wider
    const bbox = (nodes: { position: { x: number } }[]) => {
      const xs = nodes.map(n => n.position.x)
      return Math.max(...xs) - Math.min(...xs)
    }
    expect(bbox(large.nodes)).toBeGreaterThan(bbox(small.nodes))
  })
})
