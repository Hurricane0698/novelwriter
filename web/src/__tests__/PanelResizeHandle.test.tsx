import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PanelResizeHandle } from '@/components/novel-shell/PanelResizeHandle'

class TestPointerEvent extends MouseEvent {
  pointerId: number
  pointerType: string
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init)
    this.pointerId = init.pointerId ?? 1
    this.pointerType = init.pointerType ?? 'mouse'
  }
}
afterEach(() => vi.unstubAllGlobals())

function Panel({ side = 'left' }: { side?: 'left' | 'right' }) {
  const [width, setWidth] = useState(320)
  return <PanelResizeHandle side={side} width={width} min={200} max={480} onResize={setWidth} label="Resize panel" />
}

describe('PanelResizeHandle', () => {
  it.each(['mouse', 'touch', 'pen'])('resizes with %s and stops after cancellation', pointerType => {
    vi.stubGlobal('PointerEvent', TestPointerEvent)
    render(<Panel />)
    const handle = screen.getByRole('separator')
    handle.setPointerCapture = vi.fn()
    handle.releasePointerCapture = vi.fn()
    fireEvent.pointerDown(handle, { pointerType, pointerId: 1, clientX: 600, button: 0 })
    fireEvent.pointerMove(handle, { pointerType, pointerId: 1, clientX: 510 })
    expect(handle).toHaveAttribute('aria-valuenow', '410')
    fireEvent.pointerMove(handle, { pointerType, pointerId: 1, clientX: 200 })
    expect(handle).toHaveAttribute('aria-valuenow', '480')
    fireEvent.pointerCancel(handle, { pointerType, pointerId: 1 })
    fireEvent.pointerMove(handle, { pointerType, pointerId: 1, clientX: 650 })
    expect(handle).toHaveAttribute('aria-valuenow', '480')
    fireEvent.pointerDown(handle, { pointerType, pointerId: 2, clientX: 600, button: 0 })
    fireEvent.pointerMove(handle, { pointerType, pointerId: 2, clientX: 1000 })
    expect(handle).toHaveAttribute('aria-valuenow', '200')
    fireEvent.pointerUp(handle, { pointerType, pointerId: 2 })
    expect(handle.releasePointerCapture).toHaveBeenCalledWith(2)
  })

  it('moves left-side panel dividers in the direction of the arrow key', () => {
    render(<Panel side="right" />)
    const handle = screen.getByRole('separator')
    fireEvent.keyDown(handle, { key: 'ArrowRight' })
    expect(handle).toHaveAttribute('aria-valuenow', '344')
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    expect(handle).toHaveAttribute('aria-valuenow', '320')
  })
})
