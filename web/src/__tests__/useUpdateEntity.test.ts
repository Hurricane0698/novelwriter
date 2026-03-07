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
    updateEntity: vi.fn(),
  },
}))

import { worldApi } from '@/services/api'
import { useUpdateEntity } from '@/hooks/world/useEntities'

const mockUpdateEntity = worldApi.updateEntity as ReturnType<typeof vi.fn>

describe('useUpdateEntity', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('optimistically patches both entity list + entity detail without touching non-list keys', async () => {
    const novelId = 7
    const entityId = 59

    const listKey = [...worldKeys.entities(novelId), undefined]
    const detailKey = worldKeys.entity(novelId, entityId)

    const initialList = [{
      id: entityId,
      novel_id: novelId,
      name: '旧名',
      entity_type: 'Character',
      description: '旧描述',
      aliases: [],
      origin: 'manual',
      worldpack_pack_id: null,
      worldpack_key: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }]

    const initialDetail = {
      ...initialList[0],
      attributes: [],
    }

    const payload = { description: '新描述' }
    const serverEntity = {
      ...initialList[0],
      description: payload.description,
      updated_at: '2026-02-02T00:00:00Z',
    }

    let resolveUpdate: (v: typeof serverEntity) => void
    const updatePromise = new Promise<typeof serverEntity>((resolve) => {
      resolveUpdate = resolve
    })
    mockUpdateEntity.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKey, initialList)
    queryClient.setQueryData(detailKey, initialDetail)

    const { result } = renderHook(() => useUpdateEntity(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ entityId, data: payload })
    })

    // Flush one tick so onMutate runs.
    await act(async () => { await Promise.resolve() })

    expect(mockUpdateEntity).toHaveBeenCalledWith(novelId, entityId, payload)
    expect(queryClient.getQueryData(detailKey)).toMatchObject({ description: payload.description })
    expect(queryClient.getQueryData(listKey)).toMatchObject([{ id: entityId, description: payload.description }])

    resolveUpdate!(serverEntity)
    await act(async () => { await mutationPromise })

    // Final cache reflects the server response.
    expect(queryClient.getQueryData(detailKey)).toMatchObject({ description: payload.description, updated_at: serverEntity.updated_at })
    expect(queryClient.getQueryData(listKey)).toMatchObject([{ id: entityId, description: payload.description, updated_at: serverEntity.updated_at }])
  })

  it('rolls back caches and shows a toast on update error', async () => {
    const novelId = 7
    const entityId = 59

    const listKeyAll = [...worldKeys.entities(novelId), undefined]
    const listKeyCharacter = [...worldKeys.entities(novelId), { entity_type: 'Character' }]
    const detailKey = worldKeys.entity(novelId, entityId)

    const initialEntity = {
      id: entityId,
      novel_id: novelId,
      name: '旧名',
      entity_type: 'Character',
      description: '旧描述',
      aliases: [],
      origin: 'manual',
      worldpack_pack_id: null,
      worldpack_key: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }

    const initialList = [initialEntity]
    const initialDetail = { ...initialEntity, attributes: [] }

    const payload = { description: '新描述' }

    let rejectUpdate: (e: unknown) => void
    const updatePromise = new Promise((_resolve, reject) => {
      rejectUpdate = reject
    })
    mockUpdateEntity.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKeyAll, initialList)
    queryClient.setQueryData(listKeyCharacter, initialList)
    queryClient.setQueryData(detailKey, initialDetail)

    const { result } = renderHook(() => useUpdateEntity(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ entityId, data: payload })
    })

    // Flush one tick so onMutate runs.
    await act(async () => { await Promise.resolve() })

    expect(queryClient.getQueryData(detailKey)).toMatchObject({ description: payload.description })
    expect(queryClient.getQueryData(listKeyAll)).toMatchObject([{ id: entityId, description: payload.description }])
    expect(queryClient.getQueryData(listKeyCharacter)).toMatchObject([{ id: entityId, description: payload.description }])

    rejectUpdate!(new Error('update failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('update failed')
    })

    // Cache restored to the previous snapshot.
    expect(queryClient.getQueryData(detailKey)).toEqual(initialDetail)
    expect(queryClient.getQueryData(listKeyAll)).toEqual(initialList)
    expect(queryClient.getQueryData(listKeyCharacter)).toEqual(initialList)
    expect(toastMock).toHaveBeenCalledWith(LABELS.ERROR_SAVE_FAILED)
  })
})
