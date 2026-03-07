import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { worldKeys } from '@/hooks/world/keys'
import { createQueryClientWrapper, createTestQueryClient } from './helpers'
import { LABELS } from '@/constants/labels'

const toastMock = vi.hoisted(() => vi.fn())
vi.mock('@/components/world-model/shared/useToast', () => ({
  useToast: () => ({ toast: toastMock }),
}))

vi.mock('@/services/api', () => ({
  worldApi: {
    updateRelationship: vi.fn(),
  },
}))

import { worldApi } from '@/services/api'
import { useUpdateRelationship } from '@/hooks/world/useRelationships'

const mockUpdateRelationship = worldApi.updateRelationship as ReturnType<typeof vi.fn>

describe('useUpdateRelationship', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('optimistically patches all matching relationship list queries', async () => {
    const novelId = 7
    const relId = 33

    const listKeyA = [...worldKeys.relationships(novelId), { entity_id: 59 }]
    const listKeyB = [...worldKeys.relationships(novelId), { entity_id: 60 }]

    const initial = [{
      id: relId,
      novel_id: novelId,
      source_id: 59,
      target_id: 60,
      label: '旧标签',
      description: '',
      visibility: 'active',
      origin: 'manual',
      worldpack_pack_id: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }]

    const payload = { description: '新描述' }
    const serverRel = {
      ...initial[0],
      description: payload.description,
      updated_at: '2026-02-02T00:00:00Z',
    }

    let resolveUpdate: (v: typeof serverRel) => void
    const updatePromise = new Promise<typeof serverRel>((resolve) => {
      resolveUpdate = resolve
    })
    mockUpdateRelationship.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKeyA, initial)
    queryClient.setQueryData(listKeyB, initial)

    const { result } = renderHook(() => useUpdateRelationship(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ relId, data: payload })
    })

    await act(async () => { await Promise.resolve() })

    expect(mockUpdateRelationship).toHaveBeenCalledWith(novelId, relId, payload)
    expect(queryClient.getQueryData(listKeyA)).toMatchObject([{ id: relId, description: payload.description }])
    expect(queryClient.getQueryData(listKeyB)).toMatchObject([{ id: relId, description: payload.description }])

    resolveUpdate!(serverRel)
    await act(async () => { await mutationPromise })

    expect(queryClient.getQueryData(listKeyA)).toMatchObject([{ id: relId, description: payload.description, updated_at: serverRel.updated_at }])
    expect(queryClient.getQueryData(listKeyB)).toMatchObject([{ id: relId, description: payload.description, updated_at: serverRel.updated_at }])
  })

  it('rolls back caches and shows a toast on update error', async () => {
    const novelId = 7
    const relId = 33

    const listKeyA = [...worldKeys.relationships(novelId), { entity_id: 59 }]
    const listKeyB = [...worldKeys.relationships(novelId), { entity_id: 60 }]

    const initial = [{
      id: relId,
      novel_id: novelId,
      source_id: 59,
      target_id: 60,
      label: '旧标签',
      description: '',
      visibility: 'active',
      origin: 'manual',
      worldpack_pack_id: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }]

    const payload = { description: '新描述' }

    let rejectUpdate: (e: unknown) => void
    const updatePromise = new Promise((_resolve, reject) => {
      rejectUpdate = reject
    })
    mockUpdateRelationship.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKeyA, initial)
    queryClient.setQueryData(listKeyB, initial)

    const { result } = renderHook(() => useUpdateRelationship(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ relId, data: payload })
    })

    await act(async () => { await Promise.resolve() })

    expect(queryClient.getQueryData(listKeyA)).toMatchObject([{ id: relId, description: payload.description }])
    expect(queryClient.getQueryData(listKeyB)).toMatchObject([{ id: relId, description: payload.description }])

    rejectUpdate!(new Error('update failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('update failed')
    })

    expect(queryClient.getQueryData(listKeyA)).toEqual(initial)
    expect(queryClient.getQueryData(listKeyB)).toEqual(initial)
    expect(toastMock).toHaveBeenCalledWith(LABELS.ERROR_SAVE_FAILED)
  })
})
