import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedAutoSave } from '@/hooks/useDebouncedAutoSave'

describe('useDebouncedAutoSave', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('flush triggers save for pending scheduled value', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useDebouncedAutoSave<string>({ delayMs: 5000, save }))

    // Schedule a value — should NOT save immediately
    act(() => result.current.schedule('draft content'))
    expect(save).not.toHaveBeenCalled()
    expect(result.current.status).toBe('unsaved')

    // Flush — should save the pending value immediately
    await act(() => result.current.flush())
    expect(save).toHaveBeenCalledOnce()
    expect(save).toHaveBeenCalledWith('draft content')
    expect(result.current.status).toBe('saved')
  })

  it('flush is a no-op when nothing is pending', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useDebouncedAutoSave<string>({ delayMs: 5000, save }))

    await act(() => result.current.flush())
    expect(save).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('waits for an in-flight autosave and serializes the newest pending content', async () => {
    let finish!: () => void
    const save = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve })).mockResolvedValue(undefined)
    const { result } = renderHook(() => useDebouncedAutoSave({ delayMs: 3000, save }))
    act(() => { result.current.schedule('first'); vi.advanceTimersByTime(3000) })
    act(() => result.current.schedule('latest'))
    let completed = false
    let flushing!: Promise<void>
    act(() => { flushing = result.current.flush().then(() => { completed = true }) })
    expect(completed).toBe(false)
    expect(save).toHaveBeenCalledTimes(1)
    await act(async () => { finish(); await flushing })
    expect(save.mock.calls.map(call => call[0])).toEqual(['first', 'latest'])
    expect(completed).toBe(true)
    expect(result.current.status).toBe('saved')
  })

  it('retains a failed autosave for an explicit flush retry', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const { result } = renderHook(() => useDebouncedAutoSave({ delayMs: 3000, save }))
    act(() => result.current.schedule('last paragraph'))
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(result.current.status).toBe('unsaved')
    await act(() => result.current.flush())
    expect(save.mock.calls.map(call => call[0])).toEqual(['last paragraph', 'last paragraph'])
    expect(result.current.status).toBe('saved')
  })
})
