import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, copilotApi, streamContinuation, worldApi } from '@/services/api'
import { llmHeaders } from '@/services/apiClient'
import { clearSelfhostLlmConfig, setSelfhostLlmConfig } from '@/lib/selfhostLlmConfigStore'

describe('api service', () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
    vi.stubEnv('VITE_DEPLOY_MODE', 'selfhost')
    vi.restoreAllMocks()
    clearSelfhostLlmConfig()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    clearSelfhostLlmConfig()
  })

  it('getNovels fetches and parses response', async () => {
    const mockNovels = [{ id: 1, title: '测试小说', author: 'test', file_path: '/test', total_chapters: 3, created_at: '2026-01-01', updated_at: '2026-01-02' }]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(mockNovels), { status: 200 }))

    const result = await api.getNovels()
    expect(result).toEqual(mockNovels)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/novels'), expect.any(Object))
  })

  it('getNovel encodes id in URL', async () => {
    const novel = { id: 1, title: 'test', author: '', file_path: '', total_chapters: 0, created_at: '', updated_at: '' }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(novel), { status: 200 }))

    await api.getNovel('special/id')
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('special%2Fid'), expect.any(Object))
  })

  it('getAuthOptions fetches public auth options', async () => {
    const payload = {
      deploy_mode: 'hosted',
      invite_login_enabled: true,
      github_login_enabled: false,
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))

    await expect(api.getAuthOptions()).resolves.toEqual(payload)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/auth/options'), expect.any(Object))
  })

  it('activateInvite includes analytics payload when provided', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ access_token: 't', token_type: 'bearer' }), { status: 201 }))

    await api.activateInvite('CODE', 'writer', 'password123!', {
      anonymous_id: 'anon-1',
      attribution: { channel: 'longkong', invite_batch: 'batch-a' },
    })

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/invite'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          invite_code: 'CODE',
          nickname: 'writer',
          password: 'password123!',
          anonymous_id: 'anon-1',
          attribution: { channel: 'longkong', invite_batch: 'batch-a' },
        }),
      }),
    )
  })

  it('recordAnalyticsEvent posts hosted analytics payloads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 202 }))

    await expect(api.recordAnalyticsEvent({
      event: 'invite_gate_view',
      anonymous_id: 'anon-1',
      meta: { channel: 'longkong' },
    })).resolves.toEqual({ ok: true })

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/events'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          event: 'invite_gate_view',
          anonymous_id: 'anon-1',
          meta: { channel: 'longkong' },
        }),
      }),
    )
  })

  it('deleteNovel sends DELETE and handles 204', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204, headers: { 'content-length': '0' } }))

    await expect(api.deleteNovel(1)).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/novels/1'), expect.objectContaining({ method: 'DELETE' }))
  })

  it('throws ApiError on non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('Not Found', { status: 404 }))

    await expect(api.getNovels()).rejects.toThrow(ApiError)
    await vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('Not Found', { status: 404 }))
    try {
      await api.getNovels()
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(404)
    }
  })

  it('parses error detail and code from JSON response', async () => {
    const payload = { detail: { code: 'bootstrap_no_text', message: 'Novel has no non-empty chapter text to bootstrap' } }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 400,
        headers: { 'content-type': 'application/json', 'X-Request-ID': 'req_test_123' },
      })
    )

    expect.assertions(5)
    try {
      await api.getNovels()
      throw new Error('Expected api.getNovels() to throw')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      const err = e as ApiError
      expect(err.status).toBe(400)
      expect(err.code).toBe('bootstrap_no_text')
      expect(err.detail).toEqual(payload.detail)
      expect(err.requestId).toBe('req_test_123')
    }
  })

  it('does not retry structured 503 domain errors for request endpoints', async () => {
    const payload = { detail: { code: 'ai_manually_disabled', message: 'disabled' } }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 503,
        headers: { 'content-type': 'application/json', 'Retry-After': '300', 'X-Request-ID': 'req_llm_1' },
      }),
    )

    expect.assertions(4)
    try {
      await api.testLlmConnection()
    } catch (e) {
      const err = e as ApiError
      expect(err).toBeInstanceOf(ApiError)
      expect(err.code).toBe('ai_manually_disabled')
      expect(err.requestId).toBe('req_llm_1')
      expect(fetchSpy).toHaveBeenCalledTimes(1)
    }
  })

  it('getChapters fetches chapters for a novel', async () => {
    const chapters = [{ id: 1, novel_id: 1, chapter_number: 1, title: '第一章', content: '内容', created_at: '2026-01-01' }]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(chapters), { status: 200 }))

    const result = await api.getChapters(1)
    expect(result).toEqual(chapters)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/novels/1/chapters'), expect.any(Object))
  })

  it('handles empty response body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 200 }))

    const result = await api.getNovels()
    expect(result).toBeUndefined()
  })

  it('streamContinuation flushes final unterminated NDJSON line', async () => {
    const ndjson =
      '{"type":"start","variant":0,"total_variants":1}\n{"type":"done","continuation_ids":[1]}'
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ndjson))
        controller.close()
      },
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(stream, { status: 200 }))

    const events: Array<{ type: string }> = []
    for await (const e of streamContinuation(1, { num_versions: 1 })) {
      events.push(e)
    }
    expect(events.map(e => e.type)).toEqual(['start', 'done'])
  })

  it('streamContinuation throws a clearer error on malformed NDJSON', async () => {
    const ndjson = '{"type":"start","variant":0,"total_variants":1}\n{not-json}\n'
    const encoder = new TextEncoder()
    let cancelCalled = false
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ndjson))
      },
      cancel() {
        cancelCalled = true
      },
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(stream, { status: 200 }))

    const consume = async () => {
      for await (const event of streamContinuation(1, { num_versions: 1 })) {
        // consume
        void event
      }
    }
    await expect(consume()).rejects.toThrow(/Malformed NDJSON line:/)
    expect(cancelCalled).toBe(true)
  })

  it('streamContinuation does not retry structured 503 domain errors and preserves error code', async () => {
    const payload = { detail: { code: 'ai_manually_disabled', message: 'disabled' } }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 503,
        headers: { 'content-type': 'application/json', 'Retry-After': '300', 'X-Request-ID': 'req_stream_1' },
      }),
    )

    expect.assertions(4)
    try {
      for await (const event of streamContinuation(1, { num_versions: 1 })) {
        void event
      }
    } catch (e) {
      const err = e as ApiError
      expect(err).toBeInstanceOf(ApiError)
      expect(err.code).toBe('ai_manually_disabled')
      expect(err.requestId).toBe('req_stream_1')
      expect(fetchSpy).toHaveBeenCalledTimes(1)
    }
  })

  it('does not attach BYOK LLM headers to non-LLM endpoints', async () => {
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('[]', { status: 200 })) // api.getNovels
      .mockResolvedValueOnce(new Response('[]', { status: 200 })) // worldApi.listEntities

    await api.getNovels()
    await worldApi.listEntities(1)

    const init = fetchSpy.mock.calls[0][1]
    const headers = (init.headers ?? {}) as Record<string, string>

    expect(headers['X-LLM-Base-Url']).toBeUndefined()
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Model']).toBeUndefined()

    const init2 = fetchSpy.mock.calls[1][1]
    const headers2 = (init2.headers ?? {}) as Record<string, string>
    expect(headers2['X-LLM-Base-Url']).toBeUndefined()
    expect(headers2['X-LLM-Api-Key']).toBeUndefined()
    expect(headers2['X-LLM-Model']).toBeUndefined()
  })

  it.each(['hosted', 'desktop'] as const)('omits selfhost BYOK headers on %s LLM endpoints', async (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ continuations: [], debug: {} }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await api.continueNovel(1, { num_versions: 1 })
    const init = fetchSpy.mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBeUndefined()
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Model']).toBeUndefined()

    await api.testLlmConnection()
    const init2 = fetchSpy.mock.calls[1][1]
    const headers2 = init2.headers as Record<string, string>
    expect(headers2['X-LLM-Base-Url']).toBeUndefined()
    expect(headers2['X-LLM-Api-Key']).toBeUndefined()
    expect(headers2['X-LLM-Model']).toBeUndefined()
  })

  it('llmHeaders exposes BYOK config in selfhost mode', async () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'selfhost')
    clearSelfhostLlmConfig()
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    const headers = llmHeaders() as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers['X-LLM-Model']).toBe('m')
  })

  it('context-summary generation forwards BYOK while review updates do not', async () => {
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({
      id: 9,
      novel_id: 7,
      start_chapter: 1,
      end_chapter: 20,
      title: '第1—20章远期剧情回顾',
      content: '摘要',
      model: 'm',
      review_status: 'draft',
      is_stale: false,
      created_at: '2026-08-12T00:00:00Z',
      updated_at: '2026-08-12T00:00:00Z',
    }), { status: 201 }))

    await api.createContextSummary(7, 1, 20)

    const init = vi.mocked(fetch).mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers['X-LLM-Model']).toBe('m')
    expect(init.body).toBe(JSON.stringify({ start_chapter: 1, end_chapter: 20 }))

    await api.updateContextSummary(7, 9, { content: '审核后', review_status: 'confirmed' })
    const reviewHeaders = vi.mocked(fetch).mock.calls[1][1].headers as Record<string, string>
    expect(reviewHeaders['X-LLM-Api-Key']).toBeUndefined()

    await api.regenerateContextSummary(7, 9)
    const regenerateHeaders = vi.mocked(fetch).mock.calls[2][1].headers as Record<string, string>
    expect(regenerateHeaders['X-LLM-Api-Key']).toBe('sk-test')
  })

  it.each([
    {
      field: 'base URL',
      config: { baseUrl: ' https://example.com/v1 ', apiKey: 'sk-sensitive-value', model: 'm' },
      code: 'llm_base_url_invalid',
    },
    {
      field: 'API key',
      config: { baseUrl: 'https://example.com/v1', apiKey: ' sk-sensitive-value ', model: 'm' },
      code: 'llm_api_key_invalid',
    },
    {
      field: 'API key encoding',
      config: { baseUrl: 'https://example.com/v1', apiKey: 'sk-sensitive\u200bvalue', model: 'm' },
      code: 'llm_api_key_invalid',
    },
  ])('rejects selfhost $field changes before Fetch can normalize or reject them', async ({ config, code }) => {
    setSelfhostLlmConfig(config)
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    expect.assertions(5)
    try {
      await api.testLlmConnection()
      throw new Error('Expected api.testLlmConnection() to reject invalid selfhost config')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.status).toBe(400)
      expect(apiError.code).toBe(code)
      expect(JSON.stringify(apiError.detail)).not.toContain(config.apiKey)
    }
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('uses the desktop LLM config API without exposing a saved key in responses', async () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'desktop')
    const configured = {
      configured: true,
      base_url: 'https://example.com/v1',
      model: 'desktop-model',
      api_key_configured: true,
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(configured), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(configured), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await expect(api.getLlmConfig()).resolves.toEqual(configured)
    await expect(api.updateLlmConfig({
      base_url: configured.base_url,
      model: configured.model,
      api_key: 'desktop-secret',
    })).resolves.toEqual(configured)
    await expect(api.clearLlmConfig()).resolves.toBeUndefined()

    expect(fetchSpy.mock.calls[0][0]).toBe('/api/llm/config')
    expect(fetchSpy.mock.calls[1][1]).toMatchObject({
      method: 'PUT',
      body: JSON.stringify({
        base_url: configured.base_url,
        model: configured.model,
        api_key: 'desktop-secret',
      }),
    })
    expect(fetchSpy.mock.calls[2][1]).toMatchObject({ method: 'DELETE' })
    expect(configured).not.toHaveProperty('api_key')
  })

  it('tags non-stream continuation fallback requests for backend analytics', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ continuations: [], debug: {} }), { status: 200 }),
    )

    await api.continueNovel(1, { num_versions: 1 }, {
      deliveryMode: 'stream-fallback',
      continuationRequestId: 'req-123',
    })

    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-Novwr-Delivery-Mode']).toBe('stream-fallback')
    expect(headers['X-Novwr-Continuation-Request-ID']).toBe('req-123')
  })

  it.each(['hosted', 'desktop'] as const)('streamContinuation omits BYOK LLM headers in %s mode', async (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    const ndjson = '{"type":"start","variant":0,"total_variants":1}\n{"type":"done","continuation_ids":[1]}\n'
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ndjson))
        controller.close()
      },
    })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(stream, { status: 200 }))

    const events: Array<{ type: string }> = []
    for await (const e of streamContinuation(1, { num_versions: 1 }, { continuationRequestId: 'req-456' })) {
      events.push(e)
    }

    expect(events.map(e => e.type)).toEqual(['start', 'done'])
    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBeUndefined()
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Model']).toBeUndefined()
    expect(headers['X-Novwr-Continuation-Request-ID']).toBe('req-456')
  })

  it.each(['hosted', 'desktop'] as const)('triggerBootstrap omits BYOK LLM headers in %s mode', async (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          job_id: 1,
          novel_id: 1,
          status: 'pending',
          mode: 'initial',
          initialized: false,
          progress: { step: 0, detail: 'queued' },
          result: { entities_found: 0, relationships_found: 0, index_refresh_only: false },
        }),
        { status: 202 }
      )
    )

    await worldApi.triggerBootstrap(1, { mode: 'initial' })

    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBeUndefined()
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Model']).toBeUndefined()
  })

  it('sends cookies with authenticated requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))

    await api.getNovels()

    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    expect(init.credentials).toBe('include')
  })

  it('requires canonical atlas tabs when opening copilot sessions', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          session_id: 'session-1',
          signature: 'sig-1',
          mode: 'current_entity',
          scope: 'current_entity',
          context: { entity_id: 101, surface: 'atlas', tab: 'entities' },
          interaction_locale: 'zh',
          display_title: '苏瑶',
          created: false,
          created_at: '2026-03-16T00:00:00Z',
        }),
        { status: 200 },
      ),
    )

    const result = await copilotApi.openSession(1, {
      mode: 'current_entity',
      scope: 'current_entity',
      context: { entity_id: 101, surface: 'atlas', tab: 'entities' },
    })

    expect(result.context).toEqual({
      entity_id: 101,
      surface: 'atlas',
      tab: 'entities',
      stage: undefined,
    })
  })

  it('createRun forwards resume_run_id for explicit interrupted-run retries', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: 'run-2',
          status: 'queued',
          prompt: '补完苏瑶',
          trace: [],
          evidence: [],
          suggestions: [],
        }),
        { status: 202 },
      ),
    )

    await copilotApi.createRun(1, 'session-1', {
      prompt: '补完苏瑶',
      resume_run_id: 'run-1',
    })

    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({
      prompt: '补完苏瑶',
      resume_run_id: 'run-1',
    }))
  })

  it('parses copilot runs into trusted domain types', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: 'run-1',
          status: 'completed',
          prompt: '补完苏瑶',
          answer: '分析完成',
          trace: [{ step_id: 'tool_mode', kind: 'tool_mode', status: 'completed', summary: '完成' }],
          evidence: [{
            evidence_id: 'ev-1',
            source_type: 'chapter_excerpt',
            source_ref: { chapter_id: 11, chapter_number: 7, start_pos: 10, end_pos: 80 },
            title: '第7章',
            excerpt: '证据',
            why_relevant: '相关',
            pack_id: 'pk_ch_11',
            source_refs: [{ type: 'chapter', chapter_id: 11, chapter_number: 7, start_pos: 10, end_pos: 80 }],
            anchor_terms: ['帝国', '军团'],
            support_count: 2,
            preview_excerpt: '证据预览',
            expanded: true,
          }],
          suggestions: [{
            suggestion_id: 'sg-1',
            kind: 'update_entity',
            title: '补完实体',
            summary: '补全描述',
            evidence_ids: ['ev-1'],
            target: { resource: 'entity', resource_id: 101, label: '苏瑶', tab: 'entities', entity_id: 101 },
            preview: {
              target_label: '苏瑶',
              summary: '补全描述',
              field_deltas: [{ field: 'description', label: '描述', before: null, after: '新的描述' }],
              evidence_quotes: ['证据'],
              actionable: true,
            },
            apply: { type: 'update_entity', entity_id: 101, data: { description: '新的描述' } },
            status: 'pending',
          }],
          error: null,
        }),
        { status: 200 },
      ),
    )

    const result = await copilotApi.pollRun(1, 'session-1', 'run-1')
    expect(result.status).toBe('completed')
    expect(result.evidence[0]?.source_ref?.chapter_number).toBe(7)
    expect(result.evidence[0]?.pack_id).toBe('pk_ch_11')
    expect(result.evidence[0]?.expanded).toBe(true)
    expect(result.suggestions[0]?.target.tab).toBe('entities')
    expect(result.suggestions[0]?.preview.actionable).toBe(true)
  })

  it('rejects malformed copilot run payloads at the api trust boundary', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: 'run-1',
          status: 'mystery-status',
          prompt: '补完苏瑶',
          trace: [],
          evidence: [],
          suggestions: [],
        }),
        { status: 200 },
      ),
    )

    await expect(copilotApi.pollRun(1, 'session-1', 'run-1')).rejects.toThrow(/Invalid API response shape/)
  })

  it('parses copilot run history lists into trusted domain types', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            run_id: 'run-1',
            status: 'completed',
            prompt: '先总结苏瑶',
            answer: '第一轮回答',
            trace: [],
            evidence: [],
            suggestions: [],
            error: null,
          },
          {
            run_id: 'run-2',
            status: 'completed',
            prompt: '继续分析宗门',
            answer: '第二轮回答',
            trace: [],
            evidence: [],
            suggestions: [],
            error: null,
          },
        ]),
        { status: 200 },
      ),
    )

    const result = await copilotApi.listRuns(1, 'session-1')
    expect(result).toHaveLength(2)
    expect(result[0]?.run_id).toBe('run-1')
    expect(result[1]?.answer).toBe('第二轮回答')
  })
})
