import { useCallback, useEffect, useRef, useState } from 'react'
import { registerDesktopSave } from '@/lib/desktopExit'

export type AutoSaveStatus = 'idle' | 'unsaved' | 'saved'

export function useDebouncedAutoSave<T>({
  delayMs,
  save,
}: {
  delayMs: number
  save: (value: T) => Promise<void>
}) {
  const saveRef = useRef(save)
  useEffect(() => {
    saveRef.current = save
  }, [save])

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingRef = useRef<{ value: T; save: (value: T) => Promise<void>; generation: number } | null>(null)
  const inFlightRef = useRef<Promise<void> | null>(null)
  const [status, setStatus] = useState<AutoSaveStatus>('idle')

  const saveSeqRef = useRef(0)

  const clearTimer = useCallback(() => {
    if (!timerRef.current) return
    clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const cancel = useCallback(() => {
    clearTimer()
    pendingRef.current = null
    // Invalidate any in-flight save so it can't overwrite the new status.
    saveSeqRef.current += 1
    setStatus('idle')
  }, [clearTimer])

  const flush = useCallback((): Promise<void> => {
    clearTimer()
    if (inFlightRef.current) return inFlightRef.current
    // One writer per editor: an older slow response must never overwrite newer
    // text. Every flush joins the same drain, including saves already in flight.
    const drain = async () => {
      while (pendingRef.current !== null) {
        const pending = pendingRef.current
        pendingRef.current = null
        try {
          await pending.save(pending.value)
        } catch (error) {
          if (pending.generation === saveSeqRef.current) {
            pendingRef.current ??= pending // Keep failed text available for retry.
            setStatus('unsaved')
          }
          throw error
        }
        if (pending.generation === saveSeqRef.current && pendingRef.current === null) {
          setStatus('saved')
        }
      }
    }
    const promise = drain().finally(() => { inFlightRef.current = null })
    inFlightRef.current = promise
    return promise
  }, [clearTimer])

  const schedule = useCallback((value: T) => {
    pendingRef.current = { value, save: saveRef.current, generation: saveSeqRef.current }
    setStatus('unsaved')
    clearTimer()
    timerRef.current = setTimeout(() => {
      void flush().catch(() => {
        // Autosave failures keep "unsaved" state; caller may expose retry via manual save.
      })
    }, delayMs)
  }, [clearTimer, delayMs, flush])

  const saveNow = useCallback(async (value: T) => {
    pendingRef.current = { value, save: saveRef.current, generation: saveSeqRef.current }
    setStatus('unsaved')
    await flush()
  }, [flush])

  useEffect(() => registerDesktopSave(flush), [flush])
  useEffect(() => () => clearTimer(), [clearTimer])

  return { status, schedule, flush, saveNow, cancel }
}
