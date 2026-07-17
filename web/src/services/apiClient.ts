import { getSelfhostLlmConfig } from '@/lib/selfhostLlmConfigStore'
import { isSelfhostRuntime } from '@/lib/runtimeMode'

// NOTE: use nullish coalescing so `VITE_API_URL=""` stays empty (same-origin in Docker).
export const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')
const NON_RETRIABLE_503_CODES = new Set([
  'ai_manually_disabled',
  'ai_budget_hard_stop',
  'ai_budget_meter_disabled',
  'ai_budget_meter_unavailable',
])

export function isNonRetriable503Code(code: string | undefined): boolean {
  return !!code && NON_RETRIABLE_503_CODES.has(code)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function assertHeaderValuePreserved(
  name: string,
  value: string,
  code: 'llm_base_url_invalid' | 'llm_api_key_invalid',
  message: string,
): void {
  let serializedValue: string | null
  try {
    const probe = new Headers()
    probe.set(name, value)
    serializedValue = probe.get(name)
  } catch {
    serializedValue = null
  }
  if (serializedValue !== value) {
    throw new ApiError(400, 'HTTP 400', {
      code,
      detail: { code, message },
    })
  }
}

export function llmHeaders(): HeadersInit {
  if (!isSelfhostRuntime()) {
    return {}
  }
  const headers: Record<string, string> = {}
  const { baseUrl, apiKey, model } = getSelfhostLlmConfig()
  assertHeaderValuePreserved(
    'X-LLM-Base-Url',
    baseUrl,
    'llm_base_url_invalid',
    'LLM base URL cannot be represented unchanged in an HTTP header.',
  )
  assertHeaderValuePreserved(
    'X-LLM-Api-Key',
    apiKey,
    'llm_api_key_invalid',
    'LLM API key cannot be represented unchanged in an HTTP header.',
  )
  if (baseUrl) headers['X-LLM-Base-Url'] = baseUrl
  if (apiKey) headers['X-LLM-Api-Key'] = apiKey
  if (model) headers['X-LLM-Model'] = model
  return headers
}

export class ApiError extends Error {
  public detail: unknown
  public code?: string
  public requestId?: string

  constructor(
    public status: number,
    message: string,
    opts?: { detail?: unknown; code?: string; requestId?: string },
  ) {
    super(message)
    this.name = 'ApiError'
    this.detail = opts?.detail
    this.code = opts?.code
    this.requestId = opts?.requestId
  }
}

export async function parseErrorDetail(res: Response): Promise<{ detail: unknown; code?: string; requestId?: string }> {
  const requestId = res.headers.get('x-request-id') ?? res.headers.get('X-Request-ID') ?? undefined
  const text = await res.text()
  if (!text) return { detail: undefined, requestId }

  const contentType = res.headers.get('content-type') || ''
  const looksJson = contentType.includes('application/json') || text.trim().startsWith('{') || text.trim().startsWith('[')

  let body: unknown = text
  if (looksJson) {
    try {
      body = JSON.parse(text) as unknown
    } catch {
      body = text
    }
  }

  const detail = isRecord(body) && 'detail' in body ? (body as { detail?: unknown }).detail : body
  const code = isRecord(detail) && typeof detail.code === 'string' ? detail.code : undefined
  return { detail, code, requestId }
}

export async function throwApiError(res: Response): Promise<never> {
  const { detail, code, requestId } = await parseErrorDetail(res)
  // Intentionally keep message generic; UI should map (status/code) to user-facing copy.
  throw new ApiError(res.status, `HTTP ${res.status}`, { detail, code, requestId })
}

export function createApiError(
  status: number,
  parsed: { detail: unknown; code?: string; requestId?: string },
): ApiError {
  return new ApiError(status, `HTTP ${status}`, parsed)
}

export function parseRetryAfterSeconds(res: Response): number {
  const raw = parseInt(res.headers.get('Retry-After') ?? '3', 10)
  if (!Number.isFinite(raw) || raw <= 0) return 3
  return raw
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const maxRetries = 2
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      credentials: init?.credentials ?? 'include',
      // Only attach LLM BYOK headers on endpoints that actually need them.
      // This reduces accidental secret exposure via unrelated API calls / proxies / logs.
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (res.status === 503 && attempt < maxRetries) {
      const parsed = await parseErrorDetail(res)
      if (isNonRetriable503Code(parsed.code)) {
        throw createApiError(res.status, parsed)
      }
      const retryAfter = parseRetryAfterSeconds(res)
      await new Promise(r => setTimeout(r, retryAfter * 1000))
      continue
    }
    if (!res.ok) await throwApiError(res)
    if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
    const text = await res.text()
    if (!text) return undefined as T
    return JSON.parse(text) as T
  }
}

export async function requestParsed<T>(
  path: string,
  parser: (value: unknown) => T,
  init?: RequestInit,
): Promise<T> {
  return parser(await request<unknown>(path, init))
}

export async function authFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) await throwApiError(res)
  if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
  return res.json()
}

export async function fetchJson<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) await throwApiError(res)
  if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
  return res.json()
}
