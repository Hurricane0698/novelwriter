import type {
  Novel,
  Chapter,
  ChapterMeta,
  ChapterCreateRequest,
  ChapterUpdateRequest,
  ContinueRequest,
  NovelContextSummary,
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
import {
  ApiError,
  BASE_URL,
  authFetch,
  createApiError,
  fetchJson,
  isNonRetriable503Code,
  llmHeaders,
  parseErrorDetail,
  parseRetryAfterSeconds,
  request,
  throwApiError,
} from './apiClient'
import { copilotApi } from './copilotApi'

const listNovels = () => request<Novel[]>('/api/novels')
const listChapters = (novelId: number) => request<Chapter[]>(`/api/novels/${novelId}/chapters`)
const UPLOAD_CONSENT_VERSION = '2026-03-06'
export const buildContinuationRequestId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `continue_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

export interface AuthOptions {
  deploy_mode: 'hosted' | 'selfhost'
  invite_login_enabled: boolean
  github_login_enabled: boolean
}

export interface LlmConfigResponse {
  configured: boolean
  base_url: string
  model: string
  api_key_configured: boolean
}

export interface LlmConfigUpdateRequest {
  base_url: string
  model: string
  api_key?: string
}

export interface LlmProbeResponse {
  code:
    | 'llm_probe_compatible'
    | 'llm_probe_connection_failed'
    | 'llm_probe_capability_mismatch'
  model: string
  latency_ms: number
  capabilities: {
    basic: boolean
    stream: boolean
    json_mode: boolean
  }
}

export interface AnalyticsEventRequest {
  event: string
  anonymous_id?: string
  novel_id?: number
  meta?: Record<string, string | number | boolean | null>
}

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

  activateInvite: async (
    invite_code: string,
    nickname: string,
    password: string,
    opts?: {
      anonymous_id?: string
      attribution?: Record<string, string | number | boolean | null>
    },
  ) => {
    const res = await fetch(`${BASE_URL}/api/auth/invite`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        invite_code,
        nickname,
        password,
        anonymous_id: opts?.anonymous_id,
        attribution: opts?.attribution ?? {},
      }),
    })
    if (!res.ok) await throwApiError(res)
    return res.json() as Promise<{ access_token: string; token_type: string }>
  },

  getAuthOptions: () => request<AuthOptions>('/api/auth/options'),
  recordAnalyticsEvent: (payload: AnalyticsEventRequest) =>
    request<{ ok: boolean }>('/api/auth/events', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getGitHubLoginUrl: (redirectTo: string) => {
    const params = new URLSearchParams()
    if (redirectTo) params.set('redirect_to', redirectTo)
    const qs = params.toString()
    return `${BASE_URL}/api/auth/github/start${qs ? `?${qs}` : ''}`
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
  retryNovelIngest: (id: number) =>
    request<Novel>(`/api/novels/${id}/ingest/retry`, { method: 'POST' }),
  deleteNovel: (id: number) =>
    request<void>(`/api/novels/${id}`, { method: 'DELETE' }),
  uploadNovel: async (
    file: File,
    title: string,
    author = '',
    opts?: {
      sourceSurface?: string
    },
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    form.append('author', author)
    if (opts?.sourceSurface) {
      form.append('source_surface', opts.sourceSurface)
    }
    form.append('consent_acknowledged', 'true')
    form.append('consent_version', UPLOAD_CONSENT_VERSION)
    const res = await fetch(`${BASE_URL}/api/novels/upload`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
    if (!res.ok) await throwApiError(res)
    return res.json() as Promise<{ novel_id: number; status: 'accepted'; total_chapters: number | null; message: string }>
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
  listContextSummaries: (novelId: number) => (
    request<NovelContextSummary[]>(`/api/novels/${novelId}/context-summaries`)
  ),
  createContextSummary: (novelId: number, start_chapter: number, end_chapter: number) =>
    request<NovelContextSummary>(`/api/novels/${novelId}/context-summaries`, {
      method: 'POST',
      headers: llmHeaders(),
      body: JSON.stringify({ start_chapter, end_chapter }),
    }),
  updateContextSummary: (
    novelId: number,
    summaryId: number,
    data: Pick<NovelContextSummary, 'content' | 'review_status'>,
  ) => request<NovelContextSummary>(`/api/novels/${novelId}/context-summaries/${summaryId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  regenerateContextSummary: (novelId: number, summaryId: number) => (
    request<NovelContextSummary>(`/api/novels/${novelId}/context-summaries/${summaryId}/regenerate`, {
      method: 'POST',
      headers: llmHeaders(),
    })
  ),
  deleteContextSummary: (novelId: number, summaryId: number) =>
    request<void>(`/api/novels/${novelId}/context-summaries/${summaryId}`, { method: 'DELETE' }),

  continueNovel: (
    novelId: number,
    data: ContinueRequest,
    opts?: { deliveryMode?: 'sync' | 'stream-fallback'; continuationRequestId?: string },
  ) =>
    request<ContinueResponse>(`/api/novels/${novelId}/continue`, {
      method: 'POST',
      headers: {
        ...llmHeaders(),
        ...(opts?.continuationRequestId
          ? { 'X-Novwr-Continuation-Request-ID': opts.continuationRequestId }
          : {}),
        ...(opts?.deliveryMode === 'stream-fallback'
          ? { 'X-Novwr-Delivery-Mode': 'stream-fallback' }
          : {}),
      },
      body: JSON.stringify(data),
    }),

  getContinuations: (novelId: number, ids: number[]) => {
    if (ids.length === 0) return Promise.resolve([])
    return request<Continuation[]>(
      `/api/novels/${novelId}/continuations?ids=${encodeURIComponent(ids.join(','))}`,
    )
  },

  getLlmConfig: () => request<LlmConfigResponse>('/api/llm/config'),
  updateLlmConfig: (data: LlmConfigUpdateRequest) =>
    request<LlmConfigResponse>('/api/llm/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  clearLlmConfig: () => request<void>('/api/llm/config', { method: 'DELETE' }),

  testLlmConnection: () =>
    request<LlmProbeResponse>('/api/llm/test', {
      method: 'POST',
      headers: llmHeaders(),
    }),
}

export async function* streamContinuation(
  novelId: number,
  data: ContinueRequest,
  opts?: { signal?: AbortSignal; continuationRequestId?: string },
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
        ...(opts?.continuationRequestId
          ? { 'X-Novwr-Continuation-Request-ID': opts.continuationRequestId }
          : {}),
      },
      body: JSON.stringify(data),
      signal: opts?.signal,
    })
    if (resp.status === 503 && attempt < maxRetries) {
      const parsed = await parseErrorDetail(resp)
      if (isNonRetriable503Code(parsed.code)) {
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
  let streamCompleted = false
  const parseLine = (line: string): StreamEvent => {
    try {
      return JSON.parse(line) as StreamEvent
    } catch {
      const preview = line.length > 200 ? line.slice(0, 200) + '...' : line
      throw new Error(`Malformed NDJSON line: ${preview}`)
    }
  }

  try {
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
    streamCompleted = true
  } finally {
    if (!streamCompleted) {
      try {
        await reader.cancel()
      } catch {
        // Best-effort: the caller is already handling the transport failure.
      }
    }
    reader.releaseLock()
  }
}

export { ApiError, copilotApi, llmHeaders }

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
