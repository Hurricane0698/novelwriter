import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test } from '@playwright/test'
import { getDeployMode } from '../fixtures/api-helpers'

// The browser calls the real FastAPI endpoint; only the external provider is local.
let provider: Server
let baseUrl: string
let budgets: number[]

test.beforeAll(async () => {
  provider = createServer(async (req, res) => {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const body = JSON.parse(Buffer.concat(chunks).toString())
    if (body.stream) {
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      res.end(`data: ${JSON.stringify({ id: 'stream', object: 'chat.completion.chunk', created: 0,
        model: body.model, choices: [{ index: 0, delta: { content: 'ok' }, finish_reason: null }] })}\n\ndata: [DONE]\n\n`)
      return
    }
    const jsonMode = body.response_format?.type === 'json_object'
    if (jsonMode) budgets.push(body.max_tokens)
    const truncated = jsonMode && body.max_tokens < 512
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({
      id: 'completion', object: 'chat.completion', created: 0, model: body.model,
      choices: [{ index: 0, message: { role: 'assistant', content: truncated ? null : jsonMode ? '{"ok":true}' : 'ok' },
        finish_reason: truncated ? 'length' : 'stop' }],
    }))
  })
  // A fixed forwarded port also permits a browser and backend on separate hosts.
  const port = Number(process.env.E2E_PROBE_PROVIDER_PORT || 0)
  await new Promise<void>((resolve) => provider.listen(port, '127.0.0.1', resolve))
  baseUrl = `http://127.0.0.1:${(provider.address() as AddressInfo).port}/v1`
})

test.afterAll(async () => {
  if (provider) await new Promise<void>((resolve, reject) => provider.close((err) => err ? reject(err) : resolve()))
})

// Error variants are covered by test_llm_probe_reasoning.py and LlmConfigCard.test.tsx.
test('settings retries a truncated probe through the real backend', async ({ page }) => {
  test.skip(getDeployMode() !== 'selfhost', 'Selfhost settings contract')
  budgets = []
  await page.goto('/settings')
  await page.getByLabel('API Base URL').fill(baseUrl)
  await page.getByLabel('API Key', { exact: true }).fill('novwr-e2e-test-key')
  await page.getByLabel('Model Name').fill('reasoner')
  const result = page.waitForResponse((response) => response.url().endsWith('/api/llm/test'))
  await page.getByTestId('llm-config-test').click()
  expect((await (await result).json()).code).toBe('llm_probe_compatible')
  await expect(page.getByTestId('llm-config-result')).toContainText('连接与应用兼容性检测通过')
  expect(budgets).toHaveLength(2)
  expect(budgets[1]).toBeGreaterThan(budgets[0])
})
