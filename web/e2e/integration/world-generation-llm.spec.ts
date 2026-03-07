import { test, expect, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  authHeaders,
  blockExternalNoise,
  createApiSession,
  getDeployMode,
  installSession,
  readInviteCode,
} from '../fixtures/api-helpers'

const API = 'http://localhost:8000'
const AUTH_SCOPE = 'world-generation-llm'

function envFlag(name: string): boolean {
  const raw = (process.env[name] ?? '').trim().toLowerCase()
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on'
}

function parseDotEnv(content: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const idx = line.indexOf('=')
    if (idx <= 0) continue
    const key = line.slice(0, idx).trim()
    let value = line.slice(idx + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    out[key] = value
  }
  return out
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function getRepoDotEnvVars(): Record<string, string> {
  // Prefer resolving from this spec file so it still works if process.cwd() changes.
  const here = path.dirname(fileURLToPath(import.meta.url))
  const envPath = path.resolve(here, '../../../.env')
  try {
    if (!fs.existsSync(envPath)) return {}
    const content = fs.readFileSync(envPath, 'utf-8')
    return parseDotEnv(content)
  } catch {
    return {}
  }
}

function normalizeApiKey(key: string | undefined): string | null {
  const v = (key ?? '').trim()
  if (!v) return null
  const lower = v.toLowerCase()
  if (lower === 'your_openai_api_key' || lower === 'replace-me') return null
  return v
}

function hasBackendLlmKey(): boolean {
  const dotenv = getRepoDotEnvVars()
  const dotenvHasKey =
    Object.prototype.hasOwnProperty.call(dotenv, 'OPENAI_API_KEY') ||
    Object.prototype.hasOwnProperty.call(dotenv, 'openai_api_key')

  // Mirror backend precedence: .env (dotenv) overrides OS env vars if the key is present at all.
  if (dotenvHasKey) {
    return Boolean(normalizeApiKey(dotenv.OPENAI_API_KEY ?? dotenv.openai_api_key))
  }

  return Boolean(
    normalizeApiKey(process.env.OPENAI_API_KEY) ??
    normalizeApiKey(process.env.openai_api_key),
  )
}

let novelId: number
let sessionToken: string

const backendHasLlmKey = hasBackendLlmKey()
const deployMode = getDeployMode()
const inviteCode = readInviteCode()

async function apiGet(request: APIRequestContext, path: string, token: string) {
  return request.get(`${API}${path}`, { headers: authHeaders(token) })
}

async function apiDelete(request: APIRequestContext, path: string, token: string) {
  return request.delete(`${API}${path}`, { headers: authHeaders(token) })
}

async function cleanupWorldModelData(request: APIRequestContext, novelId: number, token: string) {
  // Relationship rows reference entities; delete relationships first for deterministic cleanup.
  const rels = await (await apiGet(request, `/api/novels/${novelId}/world/relationships`, token)).json()
  for (const rel of rels) {
    await apiDelete(request, `/api/novels/${novelId}/world/relationships/${rel.id}`, token)
  }

  const entities = await (await apiGet(request, `/api/novels/${novelId}/world/entities`, token)).json()
  for (const ent of entities) {
    await apiDelete(request, `/api/novels/${novelId}/world/entities/${ent.id}`, token)
  }

  const systems = await (await apiGet(request, `/api/novels/${novelId}/world/systems`, token)).json()
  for (const sys of systems) {
    await apiDelete(request, `/api/novels/${novelId}/world/systems/${sys.id}`, token)
  }
}

// Tests share a novel — run serially to avoid interference (and reduce paid LLM calls).
test.describe.configure({ mode: 'serial' })

test.describe('World generation (real LLM, integration)', () => {
  test.skip(
    deployMode === 'hosted' && !inviteCode,
    'Skipping: hosted run requires INVITE_CODE or E2E_INVITE_CODE',
  )

  test.skip(
    envFlag('E2E_SKIP_LLM') || !backendHasLlmKey,
    'Skipping: backend has no OPENAI_API_KEY configured, or E2E_SKIP_LLM=1',
  )

  test.beforeAll(async ({ request }) => {
    sessionToken = (await createApiSession(request, { scope: AUTH_SCOPE })).accessToken

    const res = await request.post(`${API}/api/novels/upload`, {
      headers: authHeaders(sessionToken),
      multipart: {
        title: 'E2E 世界生成测试小说',
        author: 'test',
        file: {
          name: 'worldgen.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('第一章 世界生成测试\n内容\n', 'utf-8'),
        },
        consent_acknowledged: 'true',
        consent_version: '2026-03-06',
      },
    })
    expect(res.ok()).toBeTruthy()
    novelId = (await res.json()).novel_id

    await cleanupWorldModelData(request, novelId, sessionToken)
  })

  test.afterAll(async ({ request }) => {
    await cleanupWorldModelData(request, novelId, sessionToken)
    await apiDelete(request, `/api/novels/${novelId}`, sessionToken)
  })

  test.beforeEach(async ({ page }) => {
    await blockExternalNoise(page)
    await installSession(page, sessionToken)
  })

  test('paste settings → 草稿审核 → confirm → entity appears', async ({ page, request }) => {
    test.slow()
    test.setTimeout(180_000)

    const seedText = [
      '【世界观设定】',
      '人物：',
      '- 张三：青云门弟子，性格谨慎。',
      '- 李四：张三的师父。',
      '势力：',
      '- 青云门：正道门派。',
      '地点：',
      '- 青云山：青云门所在。',
      '关系：',
      '- 李四 是 师父 → 张三。',
      '体系：',
      '- 修炼体系：境界分为 炼气、筑基。',
    ].join('\n')

    await page.goto(`/novel/${novelId}`)
    await expect(page.getByTestId('world-onboarding')).toBeVisible({ timeout: 15_000 })

    await page.getByTestId('world-onboarding-generate').click()
    await expect(page.getByTestId('world-gen-dialog')).toBeVisible()

    await page.getByTestId('world-gen-text').fill(seedText)
    await page.getByTestId('world-gen-submit').click()

    await expect(page).toHaveURL(new RegExp(`/world/${novelId}\\?tab=review&kind=entities`), {
      timeout: 180_000,
    })
    await expect(page.getByTestId('tab-review-indicator')).toBeVisible({ timeout: 15_000 })

    // Wait for at least one draft entity card.
    const cards = page.locator('[id^="draft-entities-"]')
    await expect(cards.first()).toBeVisible({ timeout: 120_000 })

    // Confirm all entity drafts (avoid depending on exact LLM-chosen names).
    const confirmAll = page.getByRole('button', { name: /确认\s+全部\s+\(\d+\)/ })
    await expect(confirmAll).toBeEnabled({ timeout: 15_000 })
    await confirmAll.click()

    // Draft entity cards should disappear after confirmation.
    await expect(cards).toHaveCount(0, { timeout: 30_000 })

    // Verify confirmed entity exists via API (strong backend signal).
    const entsRes = await apiGet(request, `/api/novels/${novelId}/world/entities`, sessionToken)
    expect(entsRes.ok()).toBeTruthy()
    const ents = (await entsRes.json()) as Array<{ name: string; status: string }>
    const confirmed = ents.filter((e) => e.status === 'confirmed')
    expect(confirmed.length).toBeGreaterThan(0)
    const confirmedName = confirmed[0].name

    // Confirmed entity should appear in Entities tab UI.
    await page.getByTestId('tab-entities').click()
    const sidebar = page.getByTestId('entity-sidebar')
    await sidebar.getByTestId('entity-search').fill(confirmedName)
    await expect(sidebar.getByRole('button', { name: new RegExp(escapeRegExp(confirmedName)) })).toBeVisible({ timeout: 15_000 })
  })
})
