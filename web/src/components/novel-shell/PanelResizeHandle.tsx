import { useRef } from 'react'
import { cn } from '@/lib/utils'

/** One pointer gesture for mouse, pen and touch; arrow keys move the same divider. */
export function PanelResizeHandle({ side, width, min, max, onResize, label }: {
  side: 'left' | 'right'
  width: number
  min: number
  max: number
  onResize: (width: number) => void
  label: string
}) {
  const gesture = useRef<{ pointerId: number; x: number; width: number } | null>(null)
  const direction = side === 'left' ? -1 : 1
  const resize = (next: number) => onResize(Math.round(Math.max(min, Math.min(max, next))))

  return <div
    role="separator" aria-orientation="vertical" aria-label={label}
    aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(width)} tabIndex={0}
    className={cn('nw-panel-resize absolute inset-y-0 z-40 w-3 touch-none cursor-col-resize select-none focus-visible:outline-none', side === 'left' ? 'left-0' : 'right-0')}
    onPointerDown={event => {
      if (event.button !== 0 || gesture.current) return
      event.preventDefault()
      gesture.current = { pointerId: event.pointerId, x: event.clientX, width }
      event.currentTarget.setPointerCapture(event.pointerId)
    }}
    onPointerMove={event => {
      const start = gesture.current
      if (start?.pointerId === event.pointerId) resize(start.width + direction * (event.clientX - start.x))
    }}
    onPointerUp={event => {
      if (gesture.current?.pointerId !== event.pointerId) return
      gesture.current = null
      event.currentTarget.releasePointerCapture(event.pointerId)
    }}
    onPointerCancel={() => { gesture.current = null }}
    onLostPointerCapture={() => { gesture.current = null }}
    onKeyDown={event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      event.preventDefault()
      resize(width + (event.key === 'ArrowRight' ? 24 : -24) * direction)
    }}
  />
}
