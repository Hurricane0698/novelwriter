import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { StarGraph } from '@/components/world-model/relationships/StarGraph'
import { getRelationshipTopologyKey } from '@/components/world-model/relationships/starGraphLayout'
import { layoutRelationshipGraph, type RelationshipGraphTopology } from '@/components/world-model/relationships/relationshipGraphGeometry'
import type { WorldEntity, WorldRelationship } from '@/types/api'

const { fitView, flowStore } = vi.hoisted(() => ({
  fitView: vi.fn(),
  flowStore: { width: 900, height: 650, nodeLookup: new Map([['1', { measured: { width: 144, height: 64 } }]]) },
}))
vi.mock('@/hooks/useTheme', () => ({ useTheme: () => ({ theme: 'light' }) }))
vi.mock('@/contexts/UiLocaleContext', () => ({ useUiLocale: () => ({ t: (key: string) => key }) }))
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children, nodes }: { children: ReactNode; nodes: unknown[] }) => <div><output data-testid="graph-nodes">{JSON.stringify(nodes)}</output>{children}</div>,
  useStore: (select: (store: typeof flowStore) => unknown) => select(flowStore),
  useReactFlow: () => ({ fitView, zoomIn: vi.fn(), zoomOut: vi.fn() }),
  Background: () => null, BaseEdge: () => null, EdgeLabelRenderer: () => null, Handle: () => null,
  BackgroundVariant: { Dots: 'dots' }, Position: {}, MarkerType: { ArrowClosed: 'arrowclosed' }, getBezierPath: vi.fn(),
}))

class LayoutWorker {
  static instances: LayoutWorker[] = []
  onmessage: ((event: { data: ReturnType<typeof layoutRelationshipGraph> }) => void) | null = null
  onerror: (() => void) | null = null
  terminate = vi.fn()
  postMessage = vi.fn((topology: RelationshipGraphTopology) => {
    queueMicrotask(() => this.onmessage?.({ data: layoutRelationshipGraph(topology) }))
  })
  constructor() { LayoutWorker.instances.push(this) }
}

const rel = (id: number, source_id: number, target_id: number): WorldRelationship => ({
  id, source_id, target_id, label: '认识', novel_id: 1, visibility: 'active', status: 'draft', description: '',
})
const entities = [1, 2, 3].map((id): WorldEntity => ({
  id, novel_id: 1, name: `E${id}`, entity_type: 'Character', status: 'confirmed', aliases: [], attributes: [], description: '',
}))

describe('graph geometry and camera lifecycle', () => {
  beforeEach(() => {
    LayoutWorker.instances = []
    fitView.mockClear()
    flowStore.height = 650
    flowStore.width = 900
    vi.stubGlobal('Worker', LayoutWorker)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('does not schedule geometry or fit again for selection, focus, labels, or panel dimensions', async () => {
    const relationships = [rel(1, 1, 2), rel(2, 2, 3)]
    const props = { centerId: 1, relationships, entities, onSelectEntity: vi.fn(), onSelectEdge: vi.fn(), topologyKey: getRelationshipTopologyKey(1, relationships) }
    const view = render(<StarGraph {...props} />)
    await waitFor(() => expect(fitView).toHaveBeenCalledTimes(1))
    const positions = JSON.parse(screen.getByTestId('graph-nodes').textContent!).map((node: { position: unknown }) => node.position)
    for (const selectedRelId of [1, 2, null]) {
      view.rerender(<StarGraph {...props} centerId={2} selectedRelId={selectedRelId} />)
    }
    flowStore.height = 320
    flowStore.width = 700
    view.rerender(<StarGraph {...props} relationships={relationships.map(r => ({ ...r, label: '新名称' }))} />)
    expect(LayoutWorker.instances).toHaveLength(1)
    expect(fitView).toHaveBeenCalledTimes(1)
    expect(JSON.parse(screen.getByTestId('graph-nodes').textContent!).map((node: { position: unknown }) => node.position)).toEqual(positions)

    const changed = [...relationships, rel(3, 1, 3)]
    view.rerender(<StarGraph {...props} relationships={changed} topologyKey={getRelationshipTopologyKey(1, changed)} />)
    await waitFor(() => expect(fitView).toHaveBeenCalledTimes(2))
    expect(LayoutWorker.instances).toHaveLength(2)
  })

  it('cancels pending geometry on network change and unmount', async () => {
    const props = { centerId: 1, relationships: [rel(1, 1, 2)], entities, onSelectEntity: vi.fn(), onSelectEdge: vi.fn() }
    const view = render(<StarGraph {...props} topologyKey={getRelationshipTopologyKey(1, props.relationships)} />)
    const old = LayoutWorker.instances[0]
    view.rerender(<StarGraph {...props} centerId={3} topologyKey={getRelationshipTopologyKey(3, props.relationships)} />)
    expect(old.terminate).toHaveBeenCalled()
    expect(old.onmessage).toBeNull()
    await act(async () => {})
    expect(screen.getByTestId('graph-nodes')).toHaveTextContent('E3')
    expect(screen.getByTestId('graph-nodes')).not.toHaveTextContent('E1')
    view.unmount()
    expect(LayoutWorker.instances[1].terminate).toHaveBeenCalled()
  })
})
