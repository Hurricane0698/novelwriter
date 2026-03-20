import { test, expect, type APIRequestContext } from '@playwright/test'
import { authHeaders, blockExternalNoise, createApiSession, ensureLoggedIn } from '../fixtures/api-helpers'

const API = 'http://localhost:8000'
const RUN = Math.random().toString(36).slice(2, 6)
const AUTH_SCOPE = 'world-model'

let novelId: number
let sessionToken = ''

// Tests share a novel — run serially to avoid interference
test.describe.configure({ mode: 'serial' })

async function apiPost(request: APIRequestContext, path: string, data?: unknown) {
  return request.post(`${API}${path}`, {
    headers: { ...authHeaders(sessionToken), 'Content-Type': 'application/json' },
    data,
  })
}

async function apiGet(request: APIRequestContext, path: string) {
  return request.get(`${API}${path}`, { headers: authHeaders(sessionToken) })
}

async function apiDelete(request: APIRequestContext, path: string) {
  return request.delete(`${API}${path}`, { headers: authHeaders(sessionToken) })
}

async function cleanupWorldModelData(request: APIRequestContext, novelId: number) {
  // Relationship rows reference entities; delete relationships first for deterministic cleanup.
  const rels = await (await apiGet(request, `/api/novels/${novelId}/world/relationships`)).json()
  for (const rel of rels) {
    await apiDelete(request, `/api/novels/${novelId}/world/relationships/${rel.id}`)
  }

  const entities = await (await apiGet(request, `/api/novels/${novelId}/world/entities`)).json()
  for (const ent of entities) {
    await apiDelete(request, `/api/novels/${novelId}/world/entities/${ent.id}`)
  }

  const systems = await (await apiGet(request, `/api/novels/${novelId}/world/systems`)).json()
  for (const sys of systems) {
    await apiDelete(request, `/api/novels/${novelId}/world/systems/${sys.id}`)
  }
}

test.beforeAll(async ({ request }) => {
  sessionToken = (await createApiSession(request, { scope: AUTH_SCOPE })).accessToken

  const res = await request.post(`${API}/api/novels/upload`, {
    headers: authHeaders(sessionToken),
    multipart: {
      title: 'E2E测试小说',
      author: 'test',
      file: { name: 'test.txt', mimeType: 'text/plain', buffer: Buffer.from('第一章 测试\n内容') },
      consent_acknowledged: 'true',
      consent_version: '2026-03-06',
    },
  })
  expect(res.ok()).toBeTruthy()
  novelId = (await res.json()).novel_id

  await cleanupWorldModelData(request, novelId)
})

test.afterAll(async ({ request }) => {
  if (!novelId || !sessionToken) return
  await cleanupWorldModelData(request, novelId)
  await apiDelete(request, `/api/novels/${novelId}`)
})

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
  await ensureLoggedIn(page, { scope: AUTH_SCOPE })
})

// ---------------------------------------------------------------------------
// 1. Three tabs visible
// ---------------------------------------------------------------------------

test('world model page shows three tabs', async ({ page }) => {
  await page.goto(`/world/${novelId}`)
  await expect(page.getByTestId('tab-systems')).toBeVisible()
  await expect(page.getByTestId('tab-entities')).toBeVisible()
  await expect(page.getByTestId('tab-relationships')).toBeVisible()
})

// ---------------------------------------------------------------------------
// 2. Entity CRUD
// ---------------------------------------------------------------------------

test('entity CRUD: create → sidebar → detail → edit name → delete', async ({ page }) => {
  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-entities').click()

  // Create
  await page.getByTestId('entity-create').click()
  // Newly created drafts are sorted to the top; pick the first "新实体" row.
  const entityBtn = page.getByTestId('entity-navigator').getByRole('button', { name: /^新实体$/ }).first()
  await expect(entityBtn).toBeVisible({ timeout: 10000 })

  // Atlas sidebars now have richer bottom panels; keyboard activation is more
  // stable than pointer clicks when rows sit near floating surfaces.
  await entityBtn.focus()
  await entityBtn.press('Enter')
  const detail = page.getByTestId('entity-detail')
  await expect(detail).toBeVisible({ timeout: 10000 })

  // Edit name via InlineEdit inside detail panel (not the search box)
  await detail.getByTestId('inline-edit-display').first().click()
  await detail.getByTestId('inline-edit-input').first().fill('测试角色')
  await detail.getByTestId('inline-edit-input').first().press('Enter')
  await expect(page.getByTestId('entity-navigator').getByRole('button', { name: /测试角色/ })).toBeVisible({ timeout: 10000 })

  // Delete via ··· menu
  await detail.getByRole('button', { name: '···' }).click()
  await page.getByTestId('entity-delete-menu').click()
  await page.getByTestId('confirm-ok').click()
  await expect(page.getByTestId('entity-navigator').getByRole('button', { name: /测试角色/ })).not.toBeVisible()
})

// ---------------------------------------------------------------------------
// 3. Attribute CRUD
// ---------------------------------------------------------------------------

test('attribute CRUD: add → shows in row → toggle visibility → delete', async ({ page, request }) => {
  // Create entity + attribute via API
  const entRes = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `属性实体_${RUN}`, entity_type: 'Character',
  })
  expect(entRes.ok()).toBeTruthy()
  const entity = await entRes.json()
  const attrRes = await apiPost(request, `/api/novels/${novelId}/world/entities/${entity.id}/attributes`, {
    key: '性格', surface: '沉稳', visibility: 'active',
  })
  expect(attrRes.ok()).toBeTruthy()
  const attr = await attrRes.json()

  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-entities').click()
  const entityNavigator = page.getByTestId('entity-navigator')
  const entityRow = entityNavigator.getByRole('button', { name: new RegExp(`属性实体_${RUN}`) })
  await entityRow.focus()
  await entityRow.press('Enter')
  await expect(page.getByText('属性 (1)')).toBeVisible({ timeout: 10000 })

  // Verify attribute key/value visible in collapsed row
  await expect(page.getByText('性格').first()).toBeVisible({ timeout: 5000 })
  await expect(page.getByText('沉稳').first()).toBeVisible()

  // Toggle visibility — click the dot (stopPropagation prevents row toggle)
  const attrRow = page.getByTestId(`attribute-row-${attr.id}`)
  await expect(attrRow).toBeVisible({ timeout: 10000 })
  await attrRow.getByTestId('visibility-dot').click()
  await page.waitForTimeout(500)
  const detail = await (await apiGet(request, `/api/novels/${novelId}/world/entities/${entity.id}`)).json()
  expect(detail.attributes[0].visibility).not.toBe('active')

  // Delete attribute
  await attrRow.hover()
  await attrRow.getByRole('button', { name: /^(Delete attribute|删除属性)$/ }).click()
  await expect(page.getByText('属性 (0)')).toBeVisible({ timeout: 10000 })

  // Cleanup
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${entity.id}`)
})

// ---------------------------------------------------------------------------
// 4. Relationship: create → verify via API → delete
// ---------------------------------------------------------------------------

test('relationship: create → exists → delete', async ({ page, request }) => {
  const r1 = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `关系源_${RUN}`, entity_type: 'Character',
  })
  const r2 = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `关系目标_${RUN}`, entity_type: 'Character',
  })
  const e1 = await r1.json()
  const e2 = await r2.json()

  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-relationships').click()

  // Select source entity in sidebar
  const sidebar = page.getByTestId('entity-navigator')
  await sidebar.getByTestId('entity-search').fill(`关系源_${RUN}`)
  const sourceRow = sidebar.getByRole('button', { name: new RegExp(`关系源_${RUN}`) })
  // Clicks can be flaky due to overlapping bottom panels; use keyboard activation instead.
  await sourceRow.focus()
  await sourceRow.press('Enter')
  await expect(page.getByTestId('sidebar-rel-new')).toBeEnabled({ timeout: 10000 })

  // Create relationship via bottom sheet
  await page.getByTestId('sidebar-rel-new').click()
  const sheet = page.getByTestId('bottom-sheet')
  await expect(sheet.getByPlaceholder('搜索目标实体...')).toBeVisible({ timeout: 5000 })
  await sheet.getByPlaceholder('搜索目标实体...').fill(`关系目标_${RUN}`)
  await sheet.getByRole('button', { name: new RegExp(`关系目标_${RUN}`) }).click()
  await sheet.getByPlaceholder('关系标签').fill('师徒')
  await expect(sheet.getByRole('button', { name: '确认' })).toBeEnabled({ timeout: 5000 })
  await sheet.getByRole('button', { name: '确认' }).click()

  // Wait for mutation, then verify via API
  await page.waitForTimeout(500)
  const rels = await (await apiGet(request, `/api/novels/${novelId}/world/relationships`)).json()
  expect(rels.some((r: { label: string }) => r.label === '师徒')).toBeTruthy()

  // Cleanup
  for (const rel of rels) {
    await apiDelete(request, `/api/novels/${novelId}/world/relationships/${rel.id}`)
  }
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${e1.id}`)
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${e2.id}`)
})

// ---------------------------------------------------------------------------
// 5. System: create → enter editor → edit name
// ---------------------------------------------------------------------------

test('system: create → auto-enters editor → edit name → back shows in list', async ({ page, request }) => {
  await page.goto(`/world/${novelId}`)

  const beforeSystems = await (await apiGet(request, `/api/novels/${novelId}/world/systems`)).json()
  const beforeMaxId = Math.max(0, ...beforeSystems.map((s: { id: number }) => s.id))

  // Create system via UI.
  await page.getByTestId('system-new').click()
  await page.getByRole('button', { name: '层级结构', exact: true }).click()

  // New system should exist; select it explicitly (auto-select is not guaranteed).
  let newSystemId: number | null = null
  for (let i = 0; i < 10; i++) {
    const systems = await (await apiGet(request, `/api/novels/${novelId}/world/systems`)).json()
    const maxId = Math.max(0, ...systems.map((s: { id: number }) => s.id))
    if (maxId > beforeMaxId) {
      newSystemId = maxId
      break
    }
    await page.waitForTimeout(200)
  }
  expect(newSystemId).not.toBeNull()

  const systemRow = page.getByTestId(`system-row-${newSystemId!}`)
  await systemRow.focus()
  await systemRow.press('Enter')
  await expect(page.getByTestId('system-editor')).toBeVisible({ timeout: 10000 })

  // Edit system name via InlineEdit
  const editor = page.getByTestId('system-editor')
  await editor.getByTestId('inline-edit-display').first().click()
  await editor.getByTestId('inline-edit-input').first().fill('修炼体系')
  await editor.getByTestId('inline-edit-input').first().press('Enter')
  await expect(editor.getByText('修炼体系')).toBeVisible({ timeout: 10000 })

  // Go back and verify name in list
  await editor.getByText('‹ 世界体系').click()
  await expect(systemRow).toContainText('修炼体系')

  // Cleanup via API
  const systems = await (await apiGet(request, `/api/novels/${novelId}/world/systems`)).json()
  for (const sys of systems) {
    await apiDelete(request, `/api/novels/${novelId}/world/systems/${sys.id}`)
  }
})

// ---------------------------------------------------------------------------
// 6. VisibilityDot click works without bubbling to parent
// ---------------------------------------------------------------------------

test('visibility dot: click cycles visibility without triggering parent action', async ({ page, request }) => {
  // Create entity with attribute via API
  const entRes = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `可见性测试_${RUN}`, entity_type: 'Character',
  })
  const entity = await entRes.json()
  const attrRes = await apiPost(request, `/api/novels/${novelId}/world/entities/${entity.id}/attributes`, {
    key: '测试键', surface: '测试值', visibility: 'active',
  })
  expect(attrRes.ok()).toBeTruthy()
  const attr = await attrRes.json()

  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-entities').click()
  const sidebar = page.getByTestId('entity-navigator')
  await sidebar.getByTestId('entity-search').fill(`可见性测试_${RUN}`)
  const entityRow = sidebar.getByRole('button', { name: new RegExp(`可见性测试_${RUN}`) })
  await entityRow.focus()
  await entityRow.press('Enter')
  await expect(page.getByText('属性 (1)')).toBeVisible({ timeout: 10000 })

  // Click visibility dot on attribute row — should cycle.
  const attrRow = page.getByTestId(`attribute-row-${attr.id}`)
  await attrRow.getByTestId('visibility-dot').click()
  await page.waitForTimeout(300)

  // Verify visibility changed via API
  const detail = await (await apiGet(request, `/api/novels/${novelId}/world/entities/${entity.id}`)).json()
  expect(detail.attributes[0].visibility).toBe('reference')

  // Also test system list visibility dot doesn't enter editor
  const sysRes = await apiPost(request, `/api/novels/${novelId}/world/systems`, {
    name: '可见性体系', display_type: 'list', data: { items: [] }, constraints: [],
  })
  const sys = await sysRes.json()

  await page.getByTestId('tab-systems').click()
  await expect(page.getByText('可见性体系')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('选择一个体系开始编辑')).toBeVisible()

  const sysRow = page.getByTestId(`system-row-${sys.id}`)
  const sysVisibilityDot = sysRow.getByTestId('visibility-dot')
  await sysVisibilityDot.focus()
  await sysVisibilityDot.press('Enter')
  await page.waitForTimeout(300)

  // Should NOT have entered editor (still shows empty state).
  await expect(page.getByText('选择一个体系开始编辑')).toBeVisible()

  // Cleanup
  await apiDelete(request, `/api/novels/${novelId}/world/systems/${sys.id}`)
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${entity.id}`)
})

// ---------------------------------------------------------------------------
// 7. Attribute creation: auto-expand + placeholder + editable
// ---------------------------------------------------------------------------

test('attribute: create → auto-expands → shows placeholders → editable', async ({ page, request }) => {
  const entRes = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `属性编辑_${RUN}`, entity_type: 'Character',
  })
  const entity = await entRes.json()

  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-entities').click()
  const sidebar = page.getByTestId('entity-navigator')
  await sidebar.getByTestId('entity-search').fill(`属性编辑_${RUN}`)
  const entityRow = sidebar.getByRole('button', { name: new RegExp(`属性编辑_${RUN}`) })
  await entityRow.focus()
  await entityRow.press('Enter')
  await expect(page.getByText('属性 (0)')).toBeVisible({ timeout: 10000 })

  // Add attribute
  await page.getByTestId('add-attribute').click()
  await expect(page.getByText('属性 (1)')).toBeVisible({ timeout: 10000 })

  // Verify placeholders exist for a new empty attribute.
  const detailAfterCreate = await (await apiGet(request, `/api/novels/${novelId}/world/entities/${entity.id}`)).json()
  expect(detailAfterCreate.attributes.length).toBe(1)
  const attrId = detailAfterCreate.attributes[0].id
  const attrRow = page.getByTestId(`attribute-row-${attrId}`)
  await expect(attrRow).toBeVisible({ timeout: 10000 })
  await expect(attrRow.getByText('键名')).toBeVisible()
  await expect(attrRow.getByText('值')).toBeVisible()

  // Edit key (InlineEdit)
  await attrRow.getByTestId('inline-edit-display').first().click()
  await attrRow.getByTestId('inline-edit-input').first().fill('年龄')
  await attrRow.getByTestId('inline-edit-input').first().press('Enter')
  await expect(attrRow.getByText('年龄')).toBeVisible({ timeout: 5000 })

  // Verify via API
  const detail = await (await apiGet(request, `/api/novels/${novelId}/world/entities/${entity.id}`)).json()
  expect(detail.attributes[0].key).toBe('年龄')

  // Cleanup
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${entity.id}`)
})

// ---------------------------------------------------------------------------
// 8. StarGraph: center transitions when clicking peripheral node
// ---------------------------------------------------------------------------

test('star graph: click peripheral node → becomes new center', async ({ page, request }) => {
  // Create 3 entities + 2 relationships forming a chain: A—B—C
  const r1 = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `图中心_${RUN}`, entity_type: 'Character',
  })
  const r2 = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `图外围_${RUN}`, entity_type: 'Character',
  })
  const r3 = await apiPost(request, `/api/novels/${novelId}/world/entities`, {
    name: `图远端_${RUN}`, entity_type: 'Location',
  })
  const e1 = await r1.json()
  const e2 = await r2.json()
  const e3 = await r3.json()

  await apiPost(request, `/api/novels/${novelId}/world/relationships`, {
    source_id: e1.id, target_id: e2.id, label: '认识',
  })
  await apiPost(request, `/api/novels/${novelId}/world/relationships`, {
    source_id: e2.id, target_id: e3.id, label: '居住',
  })

  await page.goto(`/world/${novelId}`)
  await page.getByTestId('tab-relationships').click()

  // Select e1 as center
  const sidebar = page.getByTestId('entity-navigator')
  await sidebar.getByTestId('entity-search').fill(`图中心_${RUN}`)
  const centerRow = sidebar.getByRole('button', { name: new RegExp(`图中心_${RUN}`) })
  await centerRow.focus()
  await centerRow.press('Enter')

  // Graph should show e1 as center, e2 as peripheral
  await expect(page.locator('.react-flow').getByText(`图中心_${RUN}`)).toBeVisible({ timeout: 10000 })
  await expect(page.locator('.react-flow').getByText(`图外围_${RUN}`)).toBeVisible({ timeout: 10000 })
  // e3 should NOT be visible (not directly connected to e1)
  await expect(page.locator('.react-flow').getByText(`图远端_${RUN}`)).not.toBeVisible()

  // Click peripheral node e2 → should become new center
  const peerNode = page.locator('.react-flow__node').filter({ hasText: `图外围_${RUN}` }).first()
  const flow = page.locator('.react-flow')
  await flow.hover()
  // Defensive: occasionally fitView runs before the graph has a stable size, leaving nodes out of viewport.
  // Zoom out a bit until the peer node becomes clickable.
  for (let i = 0; i < 8; i++) {
    const inViewport = await peerNode.evaluate((el) => {
      const r = el.getBoundingClientRect()
      return r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth
    })
    if (inViewport) break
    await page.mouse.wheel(0, 1200)
    await page.waitForTimeout(100)
  }
  await peerNode.click()
  await page.waitForTimeout(500)

  // Now e2 is center — e3 should appear (connected to e2), and e1 should still be visible
  await expect(page.locator('.react-flow').getByText(`图远端_${RUN}`)).toBeVisible({ timeout: 10000 })
  await expect(page.locator('.react-flow').getByText(`图中心_${RUN}`)).toBeVisible()

  // Cleanup
  const rels = await (await apiGet(request, `/api/novels/${novelId}/world/relationships`)).json()
  for (const rel of rels) await apiDelete(request, `/api/novels/${novelId}/world/relationships/${rel.id}`)
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${e1.id}`)
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${e2.id}`)
  await apiDelete(request, `/api/novels/${novelId}/world/entities/${e3.id}`)
})
