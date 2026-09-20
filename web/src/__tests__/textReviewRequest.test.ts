import { afterEach, expect, it, vi } from 'vitest'
import { copilotApi } from '@/services/copilotApi'
import { buildCopilotSessionSignature, type CopilotPrefill } from '@/types/copilot'

afterEach(() => vi.unstubAllGlobals())

it.each(['review_text', 'propose_world_updates'])('does not retry %s after a service failure', async (action) => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ detail: 'unavailable' }), {
    status: 503, headers: { 'content-type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetch)
  await expect(copilotApi.createRun(1, 'session', { prompt: '核对', quick_action_id: action })).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('isolates candidates while retaining a text session after edits', () => {
  const prefill: CopilotPrefill = { mode: 'research', scope: 'whole_book',
    context: { text_target: { kind: 'continuation', id: 1, content_hash: 'a'.repeat(64) } } }
  const signature = buildCopilotSessionSignature(prefill, 1, 'zh')
  expect(signature).not.toBe(buildCopilotSessionSignature({ ...prefill, context: undefined }, 1, 'zh'))
  expect(signature).toBe(buildCopilotSessionSignature({ ...prefill,
    context: { text_target: { kind: 'continuation', id: 1, content_hash: 'b'.repeat(64) } } }, 1, 'zh'))
  expect(signature).not.toBe(buildCopilotSessionSignature({ ...prefill,
    context: { text_target: { kind: 'continuation', id: 2 } } }, 1, 'zh'))
})
