export type RuntimeMode = 'selfhost' | 'desktop'

export function getRuntimeMode(): RuntimeMode {
  const rawMode = (import.meta.env.VITE_DEPLOY_MODE || 'selfhost').trim().toLowerCase()
  if (rawMode === 'selfhost' || rawMode === 'desktop') {
    return rawMode
  }
  throw new Error(`Unsupported VITE_DEPLOY_MODE: ${rawMode}`)
}

export function isSelfhostRuntime(): boolean {
  return getRuntimeMode() === 'selfhost'
}
