import { api } from '@/services/api'
import { isHostedRuntime } from '@/lib/runtimeMode'

export type HostedAnalyticsEventName =
  | 'acquisition_landing_view'
  | 'acquisition_cta_click'
  | 'invite_gate_view'
  | 'invite_gate_submit'
  | 'upload_cta_click'
  | 'world_onboarding_view'
  | 'world_onboarding_dismissed'
  | 'world_generate_open'
  | 'world_generate_submit'
  | 'world_generate_failed'
  | 'worldpack_import_submit'
  | 'worldpack_import_failed'
  | 'bootstrap_trigger'
  | 'bootstrap_failed'
  | 'demo_guide_view'
  | 'demo_guide_step_complete'
  | 'demo_guide_completed'
  | 'demo_guide_skipped'
  | 'world_model_view'
  | 'copilot_open'

export interface HostedAnalyticsContext {
  anonymous_id: string
  channel?: string
  invite_batch?: string
  entry_path?: string
  landing_path?: string
  redirect_to?: string
  referrer_host?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
}

const STORAGE_KEY = 'novwr_hosted_writer_beta_analytics_v1'

function isHostedDeployMode() {
  return isHostedRuntime()
}

function normalizeString(value: unknown, maxLength = 240): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized ? normalized.slice(0, maxLength) : undefined
}

function buildAnonymousId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `anon_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function readStoredContext(): Partial<HostedAnalyticsContext> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    return {
      anonymous_id: normalizeString(parsed.anonymous_id, 64),
      channel: normalizeString(parsed.channel, 100),
      invite_batch: normalizeString(parsed.invite_batch, 100),
      entry_path: normalizeString(parsed.entry_path, 200),
      landing_path: normalizeString(parsed.landing_path, 200),
      redirect_to: normalizeString(parsed.redirect_to, 200),
      referrer_host: normalizeString(parsed.referrer_host, 200),
      utm_source: normalizeString(parsed.utm_source, 100),
      utm_medium: normalizeString(parsed.utm_medium, 100),
      utm_campaign: normalizeString(parsed.utm_campaign, 100),
    }
  } catch {
    return {}
  }
}

function writeStoredContext(context: HostedAnalyticsContext) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(context))
  } catch {
    // best-effort only
  }
}

function currentReferrerHost(): string | undefined {
  if (typeof document === 'undefined' || !document.referrer) return undefined
  try {
    return normalizeString(new URL(document.referrer).host, 200)
  } catch {
    return undefined
  }
}

export function captureHostedAttributionFromLocation(
  locationLike: Pick<Location, 'pathname' | 'search'> | null = typeof window !== 'undefined' ? window.location : null,
): HostedAnalyticsContext | null {
  if (!isHostedDeployMode() || locationLike == null) return null

  const stored = readStoredContext()
  const params = new URLSearchParams(locationLike.search)
  const pathname = normalizeString(locationLike.pathname, 200)
  const entryPath = normalizeString(params.get('entry_path'), 200) ?? pathname
  const landingPath = pathname
  const context: HostedAnalyticsContext = {
    anonymous_id: stored.anonymous_id ?? buildAnonymousId(),
    channel: normalizeString(params.get('channel'), 100)
      ?? normalizeString(params.get('utm_source'), 100)
      ?? stored.channel,
    invite_batch: normalizeString(params.get('invite_batch'), 100)
      ?? normalizeString(params.get('batch'), 100)
      ?? normalizeString(params.get('utm_campaign'), 100)
      ?? stored.invite_batch,
    entry_path: stored.entry_path ?? entryPath,
    landing_path: stored.landing_path ?? landingPath,
    redirect_to: normalizeString(params.get('redirect_to'), 200) ?? stored.redirect_to,
    referrer_host: stored.referrer_host ?? currentReferrerHost(),
    utm_source: normalizeString(params.get('utm_source'), 100) ?? stored.utm_source,
    utm_medium: normalizeString(params.get('utm_medium'), 100) ?? stored.utm_medium,
    utm_campaign: normalizeString(params.get('utm_campaign'), 100) ?? stored.utm_campaign,
  }
  writeStoredContext(context)
  return context
}

export function snapshotHostedAnalyticsContext(): HostedAnalyticsContext | null {
  return captureHostedAttributionFromLocation()
}

function contextToAttributionMeta(context: HostedAnalyticsContext | null): Record<string, string> {
  if (!context) return {}
  const entries = Object.entries(context).filter(([key, value]) => key !== 'anonymous_id' && typeof value === 'string' && value)
  return Object.fromEntries(entries) as Record<string, string>
}

export async function trackHostedAnalyticsEvent(
  event: HostedAnalyticsEventName,
  opts?: {
    novelId?: number
    meta?: Record<string, string | number | boolean | null | undefined>
  },
): Promise<boolean> {
  const context = captureHostedAttributionFromLocation()
  if (!context) return false

  const meta: Record<string, string | number | boolean | null> = {
    ...contextToAttributionMeta(context),
    page_path: normalizeString(typeof window !== 'undefined' ? window.location.pathname : '', 200) ?? '',
  }
  for (const [key, value] of Object.entries(opts?.meta ?? {})) {
    if (typeof value === 'string') {
      const normalized = normalizeString(value)
      if (normalized) meta[key] = normalized
    } else if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
      meta[key] = value
    }
  }

  try {
    const recordAnalyticsEvent = (api as { recordAnalyticsEvent?: typeof api.recordAnalyticsEvent }).recordAnalyticsEvent
    if (typeof recordAnalyticsEvent !== 'function') return false
    await recordAnalyticsEvent({
      event,
      anonymous_id: context.anonymous_id,
      novel_id: opts?.novelId,
      meta,
    })
    return true
  } catch {
    return false
  }
}

export function buildInviteAnalyticsPayload(): {
  anonymous_id?: string
  attribution: Record<string, string>
} {
  const context = snapshotHostedAnalyticsContext()
  return {
    anonymous_id: context?.anonymous_id,
    attribution: contextToAttributionMeta(context),
  }
}
