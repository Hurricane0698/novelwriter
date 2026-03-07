export const UPLOAD_CONSENT_VERSION = '2026-03-06'

function getUploadConsentKey(userId: number | string | null | undefined): string {
  return `novwr_upload_consent_${UPLOAD_CONSENT_VERSION}:${userId ?? 'anonymous'}`
}

export function readUploadConsent(userId: number | string | null | undefined): boolean {
  try {
    return localStorage.getItem(getUploadConsentKey(userId)) === '1'
  } catch {
    return false
  }
}

export function writeUploadConsent(userId: number | string | null | undefined, accepted: boolean): void {
  try {
    const key = getUploadConsentKey(userId)
    if (accepted) localStorage.setItem(key, '1')
    else localStorage.removeItem(key)
  } catch {
    // Ignore storage failures; consent falls back to in-memory state.
  }
}

export { getUploadConsentKey }
