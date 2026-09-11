import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { RelationshipsTab } from '@/components/world-model/relationships/RelationshipsTab'
import type { WorldRelationship } from '@/types/api'

const { relationships, update, remove } = vi.hoisted(() => ({
  relationships: [
    { id: 10, source_id: 1, target_id: 2, label: 'AB' },
    { id: 20, source_id: 3, target_id: 4, label: 'CD' },
  ],
  update: vi.fn(), remove: vi.fn(),
}))
vi.mock('@/contexts/UiLocaleContext', () => ({ useUiLocale: () => ({ t: (key: string) => key }) }))
vi.mock('@/hooks/world/useRelationships', () => ({
  useWorldRelationships: () => ({ data: relationships }),
  useCreateRelationship: () => ({ mutate: vi.fn() }),
  useUpdateRelationship: () => ({ mutate: update }),
  useDeleteRelationship: () => ({ mutate: remove }),
  useConfirmRelationships: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/hooks/world/useEntities', () => ({ useWorldEntities: () => ({ data: [] }) }))
vi.mock('@/components/world-model/shared/BottomSheet', () => ({ BottomSheet: () => null }))
vi.mock('@/components/world-model/relationships/StarGraph', () => ({
  StarGraph: ({ onSelectEdge, onSelectEntity }: { onSelectEdge: (r: unknown) => void; onSelectEntity: (id: number) => void }) => <div>
    <button onClick={() => onSelectEdge(relationships[0])}>select AB</button>
    <button onClick={() => onSelectEntity(2)}>graph B</button>
  </div>,
}))
vi.mock('@/components/world-model/relationships/RelationshipInspector', () => ({
  RelationshipInspector: ({ rel, onUpdate, onDelete }: { rel: WorldRelationship; onUpdate: (id: number, data: unknown) => void; onDelete: (id: number) => void }) =>
    <div data-testid="inspector">{rel.label}<button onClick={() => onUpdate(rel.id, {})}>update selected</button><button onClick={() => onDelete(rel.id)}>delete selected</button></div>,
}))

function Harness({ externalId }: { externalId?: number }) {
  const [center, setCenter] = useState(1)
  return <><button onClick={() => setCenter(1)}>list A</button><button onClick={() => setCenter(3)}>list C</button>
    <RelationshipsTab novelId={1} selectedEntityId={center} onSelectEntity={setCenter} selectedRelationshipId={externalId} />
  </>
}

describe('relationship selection belongs to the current graph', () => {
  it('clears the old editor for both list navigation and graph node navigation', () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('select AB'))
    expect(screen.getByTestId('inspector')).toHaveTextContent('AB')
    fireEvent.click(screen.getByText('list C'))
    expect(screen.queryByTestId('inspector')).toBeNull()
    expect(screen.queryByText('update selected')).toBeNull()
    expect(screen.queryByText('delete selected')).toBeNull()
    fireEvent.click(screen.getByText('list A'))
    expect(screen.queryByTestId('inspector')).toBeNull()
    fireEvent.click(screen.getByText('select AB'))
    fireEvent.click(screen.getByText('graph B'))
    expect(screen.queryByTestId('inspector')).toBeNull()
    expect(update).not.toHaveBeenCalled()
    expect(remove).not.toHaveBeenCalled()
  })

  it('accepts external selection only in its visible network and responds to external changes', () => {
    const view = render(<Harness externalId={10} />)
    expect(screen.getByTestId('inspector')).toHaveTextContent('AB')
    view.rerender(<Harness externalId={20} />)
    expect(screen.queryByTestId('inspector')).toBeNull()
    fireEvent.click(screen.getByText('list C'))
    expect(screen.getByTestId('inspector')).toHaveTextContent('CD')
    view.rerender(<Harness />)
    expect(screen.queryByTestId('inspector')).toBeNull()
  })
})
