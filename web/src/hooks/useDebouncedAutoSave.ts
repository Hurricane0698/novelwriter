import { useCallback, useEffect, useRef, useState } from 'react'

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
  const pendingRef = useRef<T | null>(null)
  const [status, setStatus] = useState<AutoSaveStatus>('idle')

  const saveSeqRef = useRef(0)

  const clearTimer = useCallback(() => {
    if (!timerRef.current) return
    clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const runSave = useCallback(async (value: T) => {
    const seq = ++saveSeqRef.current
    try {
      await saveRef.current(value)
      // Only mark as saved if nothing newer is pending.
      if (seq === saveSeqRef.current && pendingRef.current == null) {
        setStatus('saved')
      }
    } catch (err) {
      if (seq === saveSeqRef.current) {
        setStatus('unsaved')
      }
      throw err
    }
  }, [])

  const cancel = useCallback(() => {
    clearTimer()
    pendingRef.current = null
    // Invalidate any in-flight save so it can't overwrite the new status.
    saveSeqRef.current += 1
    setStatus('idle')
  }, [clearTimer])

  const flush = useCallback(async () => {
    clearTimer()
    const pending = pendingRef.current
    if (pending == null) return
    pendingRef.current = null
    await runSave(pending)
  }, [clearTimer, runSave])

  const schedule = useCallback((value: T) => {
    pendingRef.current = value
    setStatus('unsaved')
    clearTimer()
    timerRef.current = setTimeout(() => {
      void flush().catch(() => {
        // Autosave failures keep "unsaved" state; caller may expose retry via manual save.
      })
    }, delayMs)
  }, [clearTimer, delayMs, flush])

  const saveNow = useCallback(async (value: T) => {
    clearTimer()
    pendingRef.current = null
    await runSave(value)
  }, [clearTimer, runSave])

  useEffect(() => () => clearTimer(), [clearTimer])

  return { status, schedule, flush, saveNow, cancel }
}
