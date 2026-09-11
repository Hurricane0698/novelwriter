import { useCallback, useState } from 'react'

/** Callback-ref cleanup follows panels that mount after loading or change stages. */
export function useElementWidth() {
  const [width, setWidth] = useState(0)
  const ref = useCallback((element: HTMLDivElement | null) => {
    if (!element) return
    const measure = () => setWidth(element.clientWidth)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}
