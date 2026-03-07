import { test, expect } from '@playwright/test'
import { mockAllApiRoutes } from '../fixtures/api-helpers'

function nowIso() {
  return new Date().toISOString()
}

type MockWorldEntity = {
  id: number
  novel_id: number
  name: string
  entity_type: string
  description: string
  aliases: string[]
  origin: 'manual'
  worldpack_pack_id: null
  worldpack_key: null
  status: 'draft' | 'confirmed'
  created_at: string
  updated_at: string
}

test.describe('World onboarding + world generation (mock)', () => {
  test('NovelDetailPage shows onboarding when world is empty; dismissal persists', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).toBeVisible()

    await page.getByTestId('world-onboarding-dismiss').click()
    await expect(page).toHaveURL('/world/1')

    // Back to novel detail: onboarding stays dismissed (localStorage per novel).
    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).not.toBeVisible()
  })

  test('from settings generation → draft review → confirm → entity appears', async ({ page }) => {
    await mockAllApiRoutes(page)

    // Minimal in-memory "world" for this spec file.
    const entities: MockWorldEntity[] = []
    let nextEntityId = 100

    await page.route('**/api/novels/1/world/entities**', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      const url = new URL(route.request().url())
      const status = url.searchParams.get('status')
      const data = status ? entities.filter((e) => e.status === status) : entities
      return route.fulfill({ json: data })
    })

    await page.route('**/api/novels/1/world/entities/*', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      const id = Number(route.request().url().split('/').pop())
      const entity = entities.find((e) => e.id === id)
      if (!entity) return route.fulfill({ status: 404, json: { detail: { code: 'entity_not_found' } } })
      return route.fulfill({ json: { ...entity, attributes: [] } })
    })

    await page.route('**/api/novels/1/world/generate', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      const body = route.request().postDataJSON() as { text?: string }
      if (!body.text || body.text.trim().length < 10) {
        return route.fulfill({ status: 422, json: { detail: { code: 'world_generate_text_too_short' } } })
      }
      const id = nextEntityId++
      entities.push({
        id,
        novel_id: 1,
        name: '测试角色',
        entity_type: 'Character',
        description: '',
        aliases: [],
        origin: 'manual',
        worldpack_pack_id: null,
        worldpack_key: null,
        status: 'draft',
        created_at: nowIso(),
        updated_at: nowIso(),
      })
      return route.fulfill({
        json: { entities_created: 1, relationships_created: 0, systems_created: 0, warnings: [] },
      })
    })

    await page.route('**/api/novels/1/world/entities/confirm', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      const body = route.request().postDataJSON() as { ids?: number[] }
      const ids = Array.isArray(body.ids) ? body.ids : []
      for (const id of ids) {
        const e = entities.find((x) => x.id === id)
        if (e) e.status = 'confirmed'
      }
      return route.fulfill({ json: { confirmed: ids.length } })
    })

    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).toBeVisible()

    await page.getByTestId('world-onboarding-generate').click()
    await expect(page.getByTestId('world-gen-dialog')).toBeVisible()

    await page.getByTestId('world-gen-text').fill('这里是一些世界观设定文本，长度足够触发生成。')
    await page.getByTestId('world-gen-submit').click()

    await expect(page.getByTestId('tab-review-indicator')).toBeVisible({ timeout: 10_000 })
    const card = page.locator('[id^="draft-entities-"]').filter({ hasText: '测试角色' })
    await expect(card).toBeVisible()

    // Confirm the draft entity.
    await card.getByRole('button', { name: '确认' }).click()
    await expect(card).not.toBeVisible()

    // Entity should appear in the Entities sidebar list after confirmation.
    await page.getByTestId('tab-entities').click()
    await expect(page.getByTestId('entity-sidebar').getByRole('button', { name: '测试角色' })).toBeVisible()
  })

  test('generation error shows inline in dialog', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.route('**/api/novels/1/world/generate', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      return route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/novel/1')
    await page.getByTestId('world-onboarding-generate').click()
    await page.getByTestId('world-gen-text').fill('这里是一些世界观设定文本，长度足够触发生成。')
    await page.getByTestId('world-gen-submit').click()

    await expect(page.getByTestId('world-gen-error')).toBeVisible()
  })

  test('WorldModel sidebars all show the unified build section', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.goto('/world/1')
    await expect(page.getByTestId('world-build-section')).toBeVisible()

    await page.getByTestId('tab-entities').click()
    await expect(page.getByTestId('world-build-section')).toBeVisible()

    await page.getByTestId('tab-relationships').click()
    await expect(page.getByTestId('world-build-section')).toBeVisible()
  })
})
