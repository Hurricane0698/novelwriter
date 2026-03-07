import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'

describe('useConfirmDialog', () => {
  it('starts closed', () => {
    const { result } = renderHook(() => useConfirmDialog())
    expect(result.current.dialogProps.open).toBe(false)
  })

  it('confirm() opens dialog and resolves true on confirm', async () => {
    const { result } = renderHook(() => useConfirmDialog())

    let resolved: boolean | undefined
    act(() => {
      result.current.confirm({ title: '删除？' }).then(v => { resolved = v })
    })

    expect(result.current.dialogProps.open).toBe(true)
    expect(result.current.dialogProps.title).toBe('删除？')
    expect(result.current.dialogProps.showCancel).toBe(true)

    act(() => result.current.dialogProps.onConfirm())
    await vi.waitFor(() => expect(resolved).toBe(true))
  })

  it('confirm() resolves false on close', async () => {
    const { result } = renderHook(() => useConfirmDialog())

    let resolved: boolean | undefined
    act(() => {
      result.current.confirm({ title: 'test' }).then(v => { resolved = v })
    })

    act(() => result.current.dialogProps.onClose())
    await vi.waitFor(() => expect(resolved).toBe(false))
  })

  it('alert() opens dialog without cancel button', async () => {
    const { result } = renderHook(() => useConfirmDialog())

    let alertDone = false
    act(() => {
      result.current.alert({ title: '提示' }).then(() => { alertDone = true })
    })

    expect(result.current.dialogProps.open).toBe(true)
    expect(result.current.dialogProps.showCancel).toBe(false)
    expect(result.current.dialogProps.confirmText).toBe('知道了')

    act(() => result.current.dialogProps.onConfirm())
    await vi.waitFor(() => expect(alertDone).toBe(true))
  })

  it('queues multiple dialogs', async () => {
    const { result } = renderHook(() => useConfirmDialog())

    const results: boolean[] = []
    act(() => {
      result.current.confirm({ title: 'first' }).then(v => results.push(v))
      result.current.confirm({ title: 'second' }).then(v => results.push(v))
    })

    expect(result.current.dialogProps.title).toBe('first')

    act(() => result.current.dialogProps.onConfirm())
    await vi.waitFor(() => expect(result.current.dialogProps.title).toBe('second'))

    act(() => result.current.dialogProps.onClose())
    await vi.waitFor(() => expect(results).toEqual([true, false]))
  })
})
