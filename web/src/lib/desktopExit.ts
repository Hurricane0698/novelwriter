type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>
type ExitState = { requestId: number | null; phase: 'idle' | 'saving' | 'failed' }
const saves = new Set<() => Promise<void>>()
const listeners = new Set<() => void>()
let state: ExitState = { requestId: null, phase: 'idle' }
let invoke: Invoke | undefined
let completingRequest: number | null = null

export function registerDesktopSave(save: () => Promise<void>) {
  saves.add(save)
  return () => { saves.delete(save) }
}

export const getDesktopExitState = () => state
export function subscribeDesktopExit(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

function update(next: ExitState) {
  state = next
  const root = document.getElementById('root')
  if (root) root.inert = next.phase !== 'idle'
  listeners.forEach(listener => listener())
}

export async function resolveDesktopExit(decision: 'cancel' | 'discard' | 'saved') {
  const requestId = state.requestId
  if (requestId === null || !invoke || completingRequest === requestId) return
  completingRequest = requestId
  try {
    const accepted = await invoke<boolean>('complete_exit', { requestId, decision })
    if (state.requestId !== requestId) return
    if (decision === 'cancel' || !accepted) update({ requestId: null, phase: 'idle' })
  } catch {
    if (state.requestId === requestId) update({ requestId, phase: 'failed' })
  } finally {
    if (completingRequest === requestId) completingRequest = null
  }
}

export async function saveBeforeDesktopExit() {
  const requestId = state.requestId
  if (requestId === null || state.phase === 'saving') return
  update({ requestId, phase: 'saving' })
  // All participants settle before deciding; one failed save must not abandon
  // another pending request. New editing is blocked until cancel is acknowledged.
  const results = await Promise.allSettled([...saves].map(save => Promise.resolve().then(save)))
  if (state.requestId !== requestId || completingRequest === requestId) return
  if (results.some(result => result.status === 'rejected')) update({ requestId, phase: 'failed' })
  else await resolveDesktopExit('saved')
}

export function installDesktopExit() {
  const bridge = (window as Window & { __TAURI__?: { core?: { invoke?: Invoke } } }).__TAURI__
  if (!bridge?.core?.invoke) return () => {}
  invoke = bridge.core.invoke
  const prepare = (event: Event) => {
    const requestId: unknown = (event as CustomEvent).detail?.requestId
    if (!Number.isSafeInteger(requestId) || state.requestId !== null) return
    // Blur commits input-method composition before taking the save snapshot.
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    update({ requestId: requestId as number, phase: 'failed' })
    void saveBeforeDesktopExit()
  }
  const cancelled = (event: Event) => {
    if ((event as CustomEvent).detail?.requestId === state.requestId) {
      update({ requestId: null, phase: 'idle' })
    }
  }
  window.addEventListener('novwr:prepare-exit', prepare)
  window.addEventListener('novwr:cancel-exit', cancelled)
  return () => {
    window.removeEventListener('novwr:prepare-exit', prepare)
    window.removeEventListener('novwr:cancel-exit', cancelled)
    invoke = undefined
    update({ requestId: null, phase: 'idle' })
  }
}
