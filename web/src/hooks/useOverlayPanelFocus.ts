import { useEffect, useState } from 'react'

/** Dismissible workspace panels leave the toolbar usable; covered content is inert. */
export function useOverlayPanelFocus(active: boolean) {
  const [panel, setPanel] = useState<HTMLElement | null>(null)
  useEffect(() => {
    if (!active || !panel) return
    const previous = document.activeElement
    panel.focus({ preventScroll: true })
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected
        && (panel.contains(document.activeElement) || document.activeElement === document.body)) {
        previous.focus({ preventScroll: true })
      }
    }
  }, [active, panel])
  return setPanel
}
