export const LEGAL_LAST_UPDATED = '2026年3月6日'

const configuredEmail = (import.meta.env.VITE_LEGAL_CONTACT_EMAIL ?? '').trim()

export const LEGAL_CONTACT_EMAIL = configuredEmail
export const LEGAL_CONTACT_LABEL = configuredEmail || '部署前请设置 VITE_LEGAL_CONTACT_EMAIL'

export function getLegalContactHref(): string | undefined {
  return configuredEmail ? `mailto:${configuredEmail}` : undefined
}
