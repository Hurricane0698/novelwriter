import type {
  Novel,
  Chapter,
  ChapterMeta,
  ChapterCreateRequest,
  ChapterUpdateRequest,
  ContinueRequest,
  ContinueResponse,
  Continuation,
  StreamEvent,
  QuotaResponse,
  WorldEntity,
  WorldEntityDetail,
  WorldEntityAttribute,
  WorldRelationship,
  WorldSystem,
  WorldGenerateRequest,
  WorldGenerateResponse,
  CreateEntityRequest,
  UpdateEntityRequest,
  CreateAttributeRequest,
  UpdateAttributeRequest,
  CreateRelationshipRequest,
  UpdateRelationshipRequest,
  CreateSystemRequest,
  UpdateSystemRequest,
  BatchConfirmResponse,
  BootstrapJobResponse,
  BootstrapTriggerRequest,
  WorldpackImportResponse,
  WorldpackV1,
} from '@/types/api'
import { getLlmConfig } from '@/lib/llmConfigStore'

// NOTE: use nullish coalescing so `VITE_API_URL=""` stays empty (same-origin in Docker).
const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')
const NON_RETRIABLE_503_CODES = new Set([
  'ai_manually_disabled',
  'ai_budget_hard_stop',
  'ai_budget_meter_disabled',
  'ai_budget_meter_unavailable',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function llmHeaders(): HeadersInit {
  const headers: Record<string, string> = {}
  const { baseUrl, apiKey, model } = getLlmConfig()
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

async function parseErrorDetail(res: Response): Promise<{ detail: unknown; code?: string; requestId?: string }> {
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

async function throwApiError(res: Response): Promise<never> {
  const { detail, code, requestId } = await parseErrorDetail(res)
  // Intentionally keep message generic; UI should map (status/code) to user-facing copy.
  throw new ApiError(res.status, `HTTP ${res.status}`, { detail, code, requestId })
}

function createApiError(
  status: number,
  parsed: { detail: unknown; code?: string; requestId?: string },
): ApiError {
  return new ApiError(status, `HTTP ${status}`, parsed)
}

function parseRetryAfterSeconds(res: Response): number {
  const raw = parseInt(res.headers.get('Retry-After') ?? '3', 10)
  if (!Number.isFinite(raw) || raw <= 0) return 3
  return raw
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
      if (parsed.code && NON_RETRIABLE_503_CODES.has(parsed.code)) {
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

const listNovels = () => request<Novel[]>('/api/novels')
const listChapters = (novelId: number) => request<Chapter[]>(`/api/novels/${novelId}/chapters`)

export const api = {
  login: async (username: string, password: string) => {
    const body = new URLSearchParams({ username, password })
    const res = await fetch(`${BASE_URL}/api/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!res.ok) await throwApiError(res)
    return res.json() as Promise<{ access_token: string; token_type: string }>
  },

  inviteRegister: async (invite_code: string, nickname: string) => {
    const res = await fetch(`${BASE_URL}/api/auth/invite`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invite_code, nickname }),
    })
    if (!res.ok) await throwApiError(res)
    return res.json() as Promise<{ access_token: string; token_type: string }>
  },

  getQuota: () => request<QuotaResponse>('/api/auth/quota'),

  logout: async () => {
    const res = await fetch(`${BASE_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!res.ok) await throwApiError(res)
  },

  updatePreferences: (preferences: Record<string, unknown>) =>
    request<unknown>('/api/auth/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ preferences }),
    }),

  submitFeedback: (answers: object) =>
    request<QuotaResponse>('/api/auth/feedback', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  listNovels,
  getNovels: listNovels,
  getNovel: (id: number | string) => request<Novel>(`/api/novels/${encodeURIComponent(String(id))}`),
  deleteNovel: (id: number) =>
    request<void>(`/api/novels/${id}`, { method: 'DELETE' }),
  uploadNovel: async (file: File, title: string, author = '', consentVersion = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    form.append('author', author)
    form.append('consent_acknowledged', 'true')
    form.append('consent_version', consentVersion)
    const res = await fetch(`${BASE_URL}/api/novels/upload`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
    if (!res.ok) await throwApiError(res)
    return res.json() as Promise<{ novel_id: number; total_chapters: number }>
  },

  listChaptersMeta: (novelId: number) =>
    request<ChapterMeta[]>(`/api/novels/${novelId}/chapters/meta`),
  listChapters,
  getChapters: listChapters,
  getChapter: (novelId: number, num: number) =>
    request<Chapter>(`/api/novels/${novelId}/chapters/${num}`),
  createChapter: (novelId: number, data: ChapterCreateRequest) =>
    request<Chapter>(`/api/novels/${novelId}/chapters`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateChapter: (novelId: number, num: number, data: ChapterUpdateRequest) =>
    request<Chapter>(`/api/novels/${novelId}/chapters/${num}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteChapter: (novelId: number, num: number) =>
    request<void>(`/api/novels/${novelId}/chapters/${num}`, { method: 'DELETE' }),

  continueNovel: (novelId: number, data: ContinueRequest) =>
    request<ContinueResponse>(`/api/novels/${novelId}/continue`, {
      method: 'POST',
      headers: llmHeaders(),
      body: JSON.stringify(data),
    }),

  getContinuations: (novelId: number, ids: number[]) => {
    if (ids.length === 0) return Promise.resolve([])
    return request<Continuation[]>(
      `/api/novels/${novelId}/continuations?ids=${encodeURIComponent(ids.join(','))}`,
    )
  },

  testLlmConnection: () =>
    request<{ ok: boolean; model?: string; latency_ms?: number; error?: string; message?: string; capabilities?: { basic: boolean; stream: boolean; json_mode: boolean } }>('/api/llm/test', {
      method: 'POST',
      headers: llmHeaders(),
    }),
}

export async function* streamContinuation(
  novelId: number,
  data: ContinueRequest,
  opts?: { signal?: AbortSignal },
): AsyncGenerator<StreamEvent> {
  const maxRetries = 2
  let resp: Response | null = null
  for (let attempt = 0; ; attempt++) {
    resp = await fetch(`${BASE_URL}/api/novels/${novelId}/continue/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...llmHeaders(),
      },
      body: JSON.stringify(data),
      signal: opts?.signal,
    })
    if (resp.status === 503 && attempt < maxRetries) {
      const parsed = await parseErrorDetail(resp)
      if (parsed.code && NON_RETRIABLE_503_CODES.has(parsed.code)) {
        throw createApiError(resp.status, parsed)
      }
      const retryAfter = parseRetryAfterSeconds(resp)
      await new Promise(r => setTimeout(r, retryAfter * 1000))
      continue
    }
    break
  }
  if (!resp!.ok) {
    const parsed = await parseErrorDetail(resp!)
    throw createApiError(resp!.status, parsed)
  }
  const reader = resp!.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const parseLine = (line: string): StreamEvent => {
    try {
      return JSON.parse(line) as StreamEvent
    } catch {
      const preview = line.length > 200 ? line.slice(0, 200) + '...' : line
      throw new Error(`Malformed NDJSON line: ${preview}`)
    }
  }
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()!
    for (const line of lines) {
      if (line.trim()) yield parseLine(line)
    }
  }
  const tail = buffer.trim()
  if (tail) yield parseLine(tail)
}

async function authFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) await throwApiError(res)
  if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
  return res.json()
}

async function fetchJson<T>(url: string, method: string, body?: unknown): Promise<T> {
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

export { llmHeaders }

export const worldApi = {
  // World generation
  generateWorld: (novelId: number, data: WorldGenerateRequest) =>
    request<WorldGenerateResponse>(`/api/novels/${novelId}/world/generate`, {
      method: 'POST',
      headers: llmHeaders(),
      body: JSON.stringify(data),
    }),

  // Entities
  listEntities: (novelId: number, params?: { q?: string; entity_type?: string; status?: string; origin?: string; worldpack_pack_id?: string; worldpack_key?: string }) => {
    const q = new URLSearchParams()
    if (params?.q) q.set('q', params.q)
    if (params?.entity_type) q.set('entity_type', params.entity_type)
    if (params?.status) q.set('status', params.status)
    if (params?.origin) q.set('origin', params.origin)
    if (params?.worldpack_pack_id) q.set('worldpack_pack_id', params.worldpack_pack_id)
    if (params?.worldpack_key) q.set('worldpack_key', params.worldpack_key)
    const qs = q.toString()
    return authFetch<WorldEntity[]>(`${BASE_URL}/api/novels/${novelId}/world/entities${qs ? '?' + qs : ''}`)
  },
  getEntity: (novelId: number, entityId: number) =>
    authFetch<WorldEntityDetail>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}`),
  createEntity: (novelId: number, data: CreateEntityRequest) =>
    fetchJson<WorldEntity>(`${BASE_URL}/api/novels/${novelId}/world/entities`, 'POST', data),
  updateEntity: (novelId: number, entityId: number, data: UpdateEntityRequest) =>
    fetchJson<WorldEntity>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}`, 'PUT', data),
  deleteEntity: (novelId: number, entityId: number) =>
    fetchJson<void>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}`, 'DELETE'),
  confirmEntities: (novelId: number, ids: number[]) =>
    fetchJson<BatchConfirmResponse>(`${BASE_URL}/api/novels/${novelId}/world/entities/confirm`, 'POST', { ids }),
  rejectEntities: (novelId: number, ids: number[]) =>
    fetchJson<{ rejected: number }>(`${BASE_URL}/api/novels/${novelId}/world/entities/reject`, 'POST', { ids }),

  // Attributes
  createAttribute: (novelId: number, entityId: number, data: CreateAttributeRequest) =>
    fetchJson<WorldEntityAttribute>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}/attributes`, 'POST', data),
  updateAttribute: (novelId: number, entityId: number, attrId: number, data: UpdateAttributeRequest) =>
    fetchJson<WorldEntityAttribute>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}/attributes/${attrId}`, 'PUT', data),
  deleteAttribute: (novelId: number, entityId: number, attrId: number) =>
    fetchJson<void>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}/attributes/${attrId}`, 'DELETE'),
  reorderAttributes: (novelId: number, entityId: number, order: number[]) =>
    fetchJson<void>(`${BASE_URL}/api/novels/${novelId}/world/entities/${entityId}/attributes/reorder`, 'PATCH', { order }),

  // Relationships
  listRelationships: (
    novelId: number,
    params?: {
      q?: string
      entity_id?: number
      source_id?: number
      target_id?: number
      origin?: string
      worldpack_pack_id?: string
      visibility?: string
      status?: string
    }
  ) => {
    const q = new URLSearchParams()
    if (params?.q) q.set('q', params.q)
    if (params?.entity_id != null) q.set('entity_id', String(params.entity_id))
    if (params?.source_id != null) q.set('source_id', String(params.source_id))
    if (params?.target_id != null) q.set('target_id', String(params.target_id))
    if (params?.origin) q.set('origin', params.origin)
    if (params?.worldpack_pack_id) q.set('worldpack_pack_id', params.worldpack_pack_id)
    if (params?.visibility) q.set('visibility', params.visibility)
    if (params?.status) q.set('status', params.status)
    const qs = q.toString()
    return authFetch<WorldRelationship[]>(`${BASE_URL}/api/novels/${novelId}/world/relationships${qs ? '?' + qs : ''}`)
  },
  createRelationship: (novelId: number, data: CreateRelationshipRequest) =>
    fetchJson<WorldRelationship>(`${BASE_URL}/api/novels/${novelId}/world/relationships`, 'POST', data),
  updateRelationship: (novelId: number, relId: number, data: UpdateRelationshipRequest) =>
    fetchJson<WorldRelationship>(`${BASE_URL}/api/novels/${novelId}/world/relationships/${relId}`, 'PUT', data),
  deleteRelationship: (novelId: number, relId: number) =>
    fetchJson<void>(`${BASE_URL}/api/novels/${novelId}/world/relationships/${relId}`, 'DELETE'),
  confirmRelationships: (novelId: number, ids: number[]) =>
    fetchJson<BatchConfirmResponse>(`${BASE_URL}/api/novels/${novelId}/world/relationships/confirm`, 'POST', { ids }),
  rejectRelationships: (novelId: number, ids: number[]) =>
    fetchJson<{ rejected: number }>(`${BASE_URL}/api/novels/${novelId}/world/relationships/reject`, 'POST', { ids }),

  // Systems
  listSystems: (
    novelId: number,
    params?: {
      q?: string
      origin?: string
      worldpack_pack_id?: string
      visibility?: string
      status?: string
      display_type?: string
    }
  ) => {
    const q = new URLSearchParams()
    if (params?.q) q.set('q', params.q)
    if (params?.origin) q.set('origin', params.origin)
    if (params?.worldpack_pack_id) q.set('worldpack_pack_id', params.worldpack_pack_id)
    if (params?.visibility) q.set('visibility', params.visibility)
    if (params?.status) q.set('status', params.status)
    if (params?.display_type) q.set('display_type', params.display_type)
    const qs = q.toString()
    return authFetch<WorldSystem[]>(`${BASE_URL}/api/novels/${novelId}/world/systems${qs ? '?' + qs : ''}`)
  },
  getSystem: (novelId: number, systemId: number) =>
    authFetch<WorldSystem>(`${BASE_URL}/api/novels/${novelId}/world/systems/${systemId}`),
  createSystem: (novelId: number, data: CreateSystemRequest) =>
    fetchJson<WorldSystem>(`${BASE_URL}/api/novels/${novelId}/world/systems`, 'POST', data),
  updateSystem: (novelId: number, systemId: number, data: UpdateSystemRequest) =>
    fetchJson<WorldSystem>(`${BASE_URL}/api/novels/${novelId}/world/systems/${systemId}`, 'PUT', data),
  deleteSystem: (novelId: number, systemId: number) =>
    fetchJson<void>(`${BASE_URL}/api/novels/${novelId}/world/systems/${systemId}`, 'DELETE'),
  confirmSystems: (novelId: number, ids: number[]) =>
    fetchJson<BatchConfirmResponse>(`${BASE_URL}/api/novels/${novelId}/world/systems/confirm`, 'POST', { ids }),
  rejectSystems: (novelId: number, ids: number[]) =>
    fetchJson<{ rejected: number }>(`${BASE_URL}/api/novels/${novelId}/world/systems/reject`, 'POST', { ids }),

  // Bootstrap
  triggerBootstrap: (novelId: number, data: BootstrapTriggerRequest) =>
    request<BootstrapJobResponse>(`/api/novels/${novelId}/world/bootstrap`, {
      method: 'POST',
      headers: llmHeaders(),
      body: JSON.stringify(data),
    }),
  getBootstrapStatus: (novelId: number) =>
    authFetch<BootstrapJobResponse>(`${BASE_URL}/api/novels/${novelId}/world/bootstrap/status`),

  // Worldpack
  importWorldpack: (novelId: number, payload: WorldpackV1) =>
    fetchJson<WorldpackImportResponse>(`${BASE_URL}/api/novels/${novelId}/world/worldpack/import`, 'POST', payload),
}
