import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { hashText, useTextReviewTarget } from '@/hooks/novel-copilot/useTextReviewTarget'
import type { CopilotTextTarget, TextTargetBinding } from '@/types/copilot'

const bindings = new Map<string, TextTargetBinding>()
const registerTextTarget = (target: CopilotTextTarget, binding: TextTargetBinding) => {
  const key = `${target.kind}:${target.id}`
  bindings.set(key, binding)
  return () => { if (bindings.get(key) === binding) bindings.delete(key) }
}
vi.mock('@/components/novel-copilot/NovelCopilotContext', () => ({
  useNovelCopilot: () => ({ registerTextTarget, openDrawer: vi.fn() }),
}))

beforeEach(() => { bindings.clear(); vi.stubGlobal('crypto', webcrypto) })

it('drains pending saves before applying and locks editing during the write', async () => {
  let finish!: (saved: boolean) => void
  const flush = vi.fn(() => new Promise<boolean>((resolve) => { finish = resolve }))
  const accept = vi.fn()
  const operation = vi.fn(async () => ({ content: '修改稿', content_hash: await hashText('修改稿'), before_content: '原稿' }))
  const view = renderHook(() => useTextReviewTarget({ target: { kind: 'chapter', id: 1 },
    content: '原稿', flush, accept, save: vi.fn(),
  }))
  let result!: Promise<unknown>
  act(() => { result = bindings.get('chapter:1')!.write(operation) })
  expect(operation).not.toHaveBeenCalled()
  expect(view.result.current.isLocked()).toBe(true)
  await act(async () => { finish(true); await result })
  expect(operation).toHaveBeenCalledTimes(1)
  expect(accept).toHaveBeenCalledWith(expect.objectContaining({ content: '修改稿' }))
  expect(view.result.current.isLocked()).toBe(false)
})

it('does not overwrite a later manual edit on undo', async () => {
  const save = vi.fn()
  const accept = vi.fn()
  const view = renderHook(({ content }) => useTextReviewTarget({
    target: { kind: 'continuation', id: 8 }, content, flush: async () => true, accept, save,
  }), { initialProps: { content: '应用之后' } })
  const appliedHash = await hashText('应用之后')
  view.rerender({ content: '应用后又手改' })
  await act(async () => {
    await expect(bindings.get('continuation:8')!.restore('原稿', appliedHash)).rejects.toThrow('Text changed after apply')
  })
  expect(save).not.toHaveBeenCalled()
  expect(accept).not.toHaveBeenCalled()
})

it('rejects a pending write after switching candidates', async () => {
  let finish!: (saved: boolean) => void
  const flush = () => new Promise<boolean>((resolve) => { finish = resolve })
  const operation = vi.fn()
  const view = renderHook(({ id }) => useTextReviewTarget({ target: { kind: 'continuation', id },
    content: '候选内容', flush, accept: vi.fn(), save: vi.fn(),
  }), { initialProps: { id: 1 } })
  let result!: Promise<unknown>
  act(() => { result = bindings.get('continuation:1')!.write(operation) })
  view.rerender({ id: 2 })
  await act(async () => { finish(true); await expect(result).rejects.toThrow('Text editor changed') })
  expect(operation).not.toHaveBeenCalled()
  expect(bindings.has('continuation:1')).toBe(false)
  expect(bindings.has('continuation:2')).toBe(true)
})

it('captures Unicode text and current selection only when the author starts review', async () => {
  const view = renderHook(() => useTextReviewTarget({ target: { kind: 'chapter', id: 3 },
    content: '😀林秋来到河湾书院。', flush: async () => true, accept: vi.fn(), save: vi.fn(),
    selection: () => ({ start: 1, end: 3 }),
  }))
  await act(async () => {
    const target = await bindings.get('chapter:3')!.prepare()
    expect(target).toMatchObject({ kind: 'chapter', id: 3, start: 1, end: 3,
      content_hash: await hashText('😀林秋来到河湾书院。') })
  })
  view.unmount()
  expect(bindings.size).toBe(0)
})
