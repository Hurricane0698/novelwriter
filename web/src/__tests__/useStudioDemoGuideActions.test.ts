import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useStudioDemoGuideActions } from '@/hooks/novel/useStudioDemoGuideActions'

describe('useStudioDemoGuideActions', () => {
  it('reopens the demo guide through the manual-open seam', () => {
    const openManualDemoGuide = vi.fn()

    const { result } = renderHook(() => useStudioDemoGuideActions({
      visitDemoGuideStep: vi.fn(),
      openManualDemoGuide,
      openDemoChapter: vi.fn(),
      openDemoWriteStage: vi.fn(),
      openDemoAtlas: vi.fn(),
      openDemoCopilot: vi.fn(),
    }))

    act(() => {
      result.current.handleReopenDemoGuide()
    })

    expect(openManualDemoGuide).toHaveBeenCalledTimes(1)
  })

  it('marks the matching step before forwarding the demo CTA callback', () => {
    const visitDemoGuideStep = vi.fn()
    const openDemoWriteStage = vi.fn()

    const { result } = renderHook(() => useStudioDemoGuideActions({
      visitDemoGuideStep,
      openManualDemoGuide: vi.fn(),
      openDemoChapter: vi.fn(),
      openDemoWriteStage,
      openDemoAtlas: vi.fn(),
      openDemoCopilot: vi.fn(),
    }))

    act(() => {
      result.current.handleOpenDemoWriteStage()
    })

    expect(visitDemoGuideStep).toHaveBeenCalledWith('write')
    expect(openDemoWriteStage).toHaveBeenCalledTimes(1)
  })
})
