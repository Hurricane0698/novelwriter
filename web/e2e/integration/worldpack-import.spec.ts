import { test, expect, type APIRequestContext } from '@playwright/test'
import { authHeaders, blockExternalNoise, createApiSession, ensureLoggedIn } from '../fixtures/api-helpers'

const API = 'http://localhost:8000'
const RUN = Math.random().toString(36).slice(2, 6)
const AUTH_SCOPE = 'worldpack-import'

let novelId: number
let sessionToken = ''

test.describe.configure({ mode: 'serial' })

async function apiDelete(request: APIRequestContext, path: string) {
  return request.delete(`${API}${path}`, { headers: authHeaders(sessionToken) })
}

test.beforeAll(async ({ request }) => {
  sessionToken = (await createApiSession(request, { scope: AUTH_SCOPE })).accessToken

  const upload = await request.post(`${API}/api/novels/upload`, {
    headers: authHeaders(sessionToken),
    multipart: {
      title: 'E2E worldpack import',
      author: 'test',
      file: {
        name: 'worldpack-import.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('第一章 世界包导入测试\n内容\n', 'utf-8'),
      },
      consent_acknowledged: 'true',
      consent_version: '2026-03-06',
    },
  })
  expect(upload.ok()).toBeTruthy()
  novelId = (await upload.json()).novel_id
})

test.afterAll(async ({ request }) => {
  if (!novelId || !sessionToken) return
  await apiDelete(request, `/api/novels/${novelId}`)
})

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
  await ensureLoggedIn(page, { scope: AUTH_SCOPE })
})

test('import worldpack from onboarding dialog populates world model', async ({ page }) => {
  await page.goto(`/novel/${novelId}`)
  await expect(page.getByTestId('world-onboarding')).toBeVisible({ timeout: 15_000 })

  // Open the world generation / import dialog.
  await page.getByTestId('world-onboarding-generate').click()
  await expect(page.getByTestId('world-gen-dialog')).toBeVisible()

  const entityName = `测试角色_${RUN}`
  const systemName = `体系_${RUN}`

  const worldpack = {
    schema_version: 'worldpack.v1',
    pack_id: `e2e_pack_${Date.now()}_${RUN}`,
    pack_name: `E2E Pack ${RUN}`,
    language: 'zh',
    license: 'CC0-1.0',
    source: { wiki_base_url: 'https://example.com/wiki' },
    generated_at: new Date().toISOString(),
    entities: [
      {
        key: 'hero',
        name: entityName,
        entity_type: 'Character',
        description: '主角',
        aliases: ['Alpha'],
        attributes: [
          { key: 'age', surface: '18', truth: null, visibility: 'reference' },
        ],
      },
    ],
    relationships: [],
    systems: [
      {
        name: systemName,
        display_type: 'list',
        description: '境界设定',
        data: {
          items: [
            { id: 'stage-1', label: '炼气', description: '入门', visibility: 'active' },
          ],
        },
        constraints: [],
        visibility: 'active',
      },
    ],
  }

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('world-gen-import-link').click(),
  ])
  await chooser.setFiles({
    name: `worldpack_${RUN}.json`,
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(worldpack), 'utf-8'),
  })

  // On success we navigate to /world/:id.
  await expect(page).toHaveURL(new RegExp(`/world/${novelId}$`), { timeout: 30_000 })

  // Default tab is systems — verify the imported system appears.
  await expect(page.getByTestId('system-search')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('system-search').fill(systemName)
  await expect(page.locator('[data-testid^="system-row-"]').filter({ hasText: systemName })).toBeVisible()

  // Verify the imported entity appears in the Entities tab.
  await page.getByTestId('tab-entities').click()
  await expect(page.getByTestId('entity-sidebar')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('entity-sidebar').getByTestId('entity-search').fill(entityName)
  await expect(
    page.getByTestId('entity-sidebar').getByRole('button', { name: new RegExp(entityName) }),
  ).toBeVisible()
})
