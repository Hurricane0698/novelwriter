import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, ApiError, streamContinuation, worldApi } from '@/services/api'
import { clearLlmConfig, setLlmConfig } from '@/lib/llmConfigStore'

describe('api service', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    clearLlmConfig()
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
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ndjson))
        controller.close()
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
    setLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

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

  it('attaches BYOK LLM headers to LLM endpoints only', async () => {
    setLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ continuations: [], debug: {} }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await api.continueNovel(1, { num_versions: 1 })
    const init = fetchSpy.mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers['X-LLM-Model']).toBe('m')

    await api.testLlmConnection()
    const init2 = fetchSpy.mock.calls[1][1]
    const headers2 = init2.headers as Record<string, string>
    expect(headers2['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers2['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers2['X-LLM-Model']).toBe('m')
  })

  it('streamContinuation attaches BYOK LLM headers', async () => {
    setLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

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
    for await (const e of streamContinuation(1, { num_versions: 1 })) {
      events.push(e)
    }

    expect(events.map(e => e.type)).toEqual(['start', 'done'])
    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    const headers = init.headers as Record<string, string>
    expect(headers['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers['X-LLM-Model']).toBe('m')
  })

  it('triggerBootstrap attaches BYOK LLM headers', async () => {
    setLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })

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
    expect(headers['X-LLM-Base-Url']).toBe('http://example.com/v1')
    expect(headers['X-LLM-Api-Key']).toBe('sk-test')
    expect(headers['X-LLM-Model']).toBe('m')
  })

  it('sends cookies with authenticated requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))

    await api.getNovels()

    const init = (fetch as unknown as { mock: { calls: Array<[string, RequestInit]> } }).mock.calls[0][1]
    expect(init.credentials).toBe('include')
  })
})
