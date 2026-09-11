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

  it('keeps self-referencing relationships without duplicate node IDs', () => {
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

  it('expands the neighborhood when more labels need space', () => {
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
    expect(new Set(large.nodes.map(node => node.id)).size).toBe(large.nodes.length)
    // Bounding box of large graph should be wider
    const bbox = (nodes: { position: { x: number } }[]) => {
      const xs = nodes.map(n => n.position.x)
      return Math.max(...xs) - Math.min(...xs)
    }
    expect(bbox(large.nodes)).toBeGreaterThan(bbox(small.nodes))
  })
  it('includes real network links while excluding disconnected entities', () => {
    const entities = new Map([1, 2, 3, 4, 5].map(id => [id, entity(id, `Entity ${id}`)]))
    const relationships = [rel(1, 1, 2), rel(2, 1, 3), rel(3, 2, 3), rel(5, 4, 5)]
    const graph = buildGraph(1, relationships, entities)
    expect(graph.nodes.map(node => node.id)).toEqual(['1', '2', '3'])
    expect(graph.edges.map(edge => edge.id)).toEqual(['rel-1', 'rel-2', 'rel-3'])
    expect(graph.edges[2]).toMatchObject({ source: '2', target: '3' })
    expect(buildGraph(1, [...relationships].reverse(), entities).nodes).toEqual(graph.nodes)
    expect(buildGraph(2, relationships, entities).nodes.map(n => ({ id: n.id, position: n.position })))
      .toEqual(graph.nodes.map(n => ({ id: n.id, position: n.position })))
  })

  it('follows connected relationships beyond the selected entity', () => {
    const entities = new Map([1, 2, 3, 4].map(id => [id, entity(id, `Entity ${id}`)]))
    expect(buildGraph(1, [rel(1, 1, 2), rel(2, 2, 3), rel(3, 3, 4)], entities).nodes.map(n => n.id)).toEqual(['1', '2', '3', '4'])
  })

  it('keeps dense labels apart and does not rearrange nodes when a relationship is selected', () => {
    const entities = new Map(Array.from({ length: 24 }, (_, id) => [id, entity(id, `Entity ${id}`)]))
    const relationships = Array.from({ length: 23 }, (_, index) => rel(index + 1, 0, index + 1))
    const graph = buildGraph(0, relationships, entities)
    expect(buildGraph(0, relationships, entities, 4).nodes).toEqual(graph.nodes)
    graph.nodes.forEach((node, index) => graph.nodes.slice(index + 1).forEach(other => {
      const dx = Math.abs(node.position.x - other.position.x)
      const dy = Math.abs(node.position.y - other.position.y)
      expect(dx >= 169 || dy >= 89).toBe(true)
    }))
  })

})
