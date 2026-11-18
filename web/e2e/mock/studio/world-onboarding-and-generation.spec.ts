import { test, expect } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'
import { CHAPTERS } from '../../fixtures/data'

function nowIso() {
  return new Date().toISOString()
}

async function mockChapterReadyStudio(page: import('@playwright/test').Page) {
  await page.route('**/api/novels/1', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({
      json: {
        id: 1,
        title: '三体',
        author: '刘慈欣',
        file_path: '/novels/1',
        content_format: 'plain_text',
        total_chapters: 2,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'normal',
            source_bytes: 128,
            source_chars: 64,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'immediate',
            bootstrap_plan: 'immediate',
            readiness_mode: 'full_target',
            error_code: null,
            error: null,
          },
          job: null,
        },
      },
    })
  })
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
  test('late generation refreshes world data without changing the editor route or unsaved draft', async ({ page }) => {
    await mockAllApiRoutes(page)
    await mockChapterReadyStudio(page)
    let finishGeneration!: () => void
    const generationReady = new Promise<void>((resolve) => { finishGeneration = resolve })
    let generated = false
    let worldRefreshes = 0
    let saveCount = 0
    let chapter = { ...CHAPTERS[0] }
    await page.route('**/api/novels/1/chapters/1', async (route) => {
      if (route.request().method() === 'PUT') {
        saveCount += 1
        chapter = { ...chapter, ...route.request().postDataJSON() }
      }
      await route.fulfill({ json: chapter })
    })
    await page.route('**/api/novels/1/world/entities**', async (route) => {
      if (generated) worldRefreshes += 1
      await route.fulfill({ json: generated ? [{
        id: 101, novel_id: 1, name: '迟到的角色', entity_type: 'Character',
        description: '', aliases: [], origin: 'manual', status: 'draft',
        worldpack_pack_id: null, worldpack_key: null, created_at: nowIso(), updated_at: nowIso(),
      }] : [] })
    })
    await page.route('**/api/novels/1/world/generate', async (route) => {
      await generationReady
      generated = true
      await route.fulfill({ json: { entities_created: 1, relationships_created: 0, systems_created: 0, warnings: [] } })
    })
    await page.goto('/novel/1?chapter=1')
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    const editor = page.getByTestId('chapter-editor-textarea')
    await expect(editor).toBeVisible()
    const trigger = page.getByTestId('world-build-generate')
    await trigger.click()
    await page.getByTestId('world-gen-text').fill('一份足够长的世界设定，用于验证迟到的生成结果。')
    const started = page.waitForRequest('**/world/generate')
    await page.getByTestId('world-gen-submit').click()
    await started
    await page.getByTestId('world-gen-dialog').getByRole('button', { name: '取消', exact: true }).click()
    await expect(trigger).toBeFocused()
    await expect(page.getByTestId('world-gen-text')).toHaveCount(0)
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press('Tab')
      expect(await page.evaluate(() => {
        const focused = document.activeElement
        return focused === document.body || (focused instanceof HTMLElement
          && focused.getBoundingClientRect().width > 0 && getComputedStyle(focused).visibility === 'visible')
      })).toBe(true)
    }
    await page.clock.install({ time: new Date('2026-01-01T12:00:00Z') })
    await page.clock.pauseAt(new Date('2026-01-01T12:01:00Z'))
    const draft = '这段正文还没有到三秒自动保存时间，不能被迟到的生成结果覆盖。'
    const editorUrl = page.url()
    await editor.fill(draft)
    finishGeneration()
    await expect.poll(() => worldRefreshes).toBeGreaterThan(0)
    await page.clock.runFor(1)
    await expect(page).toHaveURL(editorUrl)
    await expect(editor).toHaveValue(draft)
    expect(saveCount).toBe(0)
    await page.clock.runFor(3100)
    await expect.poll(() => saveCount).toBe(1)
    expect(chapter.content).toBe(draft)
    await page.clock.resume()
    await page.reload()
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    await expect(editor).toHaveValue(draft)
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

    await page.getByTestId('world-build-generate').click()
    await expect(page.getByTestId('world-gen-dialog')).toBeVisible()

    await page.getByTestId('world-gen-text').fill('这里是一些世界观设定文本，长度足够触发生成。')
    await page.getByTestId('world-gen-submit').click()

    await page.getByTestId('studio-world-entry-attention-action').click()
    await expect(page.getByTestId('tab-review-indicator')).toBeVisible({ timeout: 10_000 })
    const card = page.locator('[id^="draft-entities-"]').filter({ hasText: '测试角色' })
    await expect(card).toBeVisible()

    // Confirm the draft entity.
    await card.getByRole('button', { name: '确认' }).click()
    await expect(card).not.toBeVisible()

    // Entity should appear in the Entities sidebar list after confirmation.
    await page.getByTestId('tab-entities').click()
    await expect(page.getByTestId('entity-navigator').getByRole('button', { name: '测试角色' })).toBeVisible()
  })

  test('generation error shows inline in dialog', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.route('**/api/novels/1/world/generate', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      return route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/novel/1')
    await page.getByTestId('world-build-generate').click()
    await page.getByTestId('world-gen-text').fill('这里是一些世界观设定文本，长度足够触发生成。')
    await page.getByTestId('world-gen-submit').click()

    await expect(page.getByTestId('world-gen-error')).toBeVisible()
  })

  test('chapters remain readable during extraction after a reload', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAllApiRoutes(page)
    await mockChapterReadyStudio(page)

    await page.route('**/api/novels/1/world/bootstrap/status', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      return route.fulfill({
        json: {
          job_id: 61,
          novel_id: 1,
          mode: 'initial',
          initialized: false,
          status: 'extracting',
          progress: { step: 2, detail: 'Extracting...' },
          result: {
            entities_found: 0,
            relationships_found: 0,
            index_refresh_only: false,
          },
          error: null,
          created_at: nowIso(),
          updated_at: nowIso(),
        },
      })
    })

    const pendingAt = Date.now()
    await page.goto(`/novel/1?worldEntryPending=extract&worldEntryPendingAt=${pendingAt}&worldEntryPendingJob=61`)

    await expect(page.getByTestId('studio-workspace-toolbar')).toBeVisible()

    await page.reload()

    await expect(page.getByTestId('studio-workspace-toolbar')).toBeVisible()
  })

  test('repeated Atlas handoff clicks navigate once and keep the review target stable', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAllApiRoutes(page)
    await mockChapterReadyStudio(page)

    await page.route('**/api/novels/1/world/entities**', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      return route.fulfill({
        json: [{
          id: 101,
          novel_id: 1,
          name: '测试角色',
          entity_type: 'Character',
          description: '',
          aliases: [],
          origin: 'manual',
          worldpack_pack_id: null,
          worldpack_key: null,
          status: 'confirmed',
          created_at: nowIso(),
          updated_at: nowIso(),
        }],
      })
    })

    await page.goto('/novel/1?worldEntryHandoff=extract_review&worldEntryEntities=2&worldEntryRelationships=1')

    const openAtlasReview = page.getByTestId('studio-world-entry-handoff-action')
    await expect(openAtlasReview).toBeVisible()

    await openAtlasReview.click()
    await openAtlasReview.click({ force: true }).catch(() => {})

    await expect(page).toHaveURL(/\/world\/1\?/)
    await expect(page).toHaveURL(/tab=review/)
    await expect(page).toHaveURL(/kind=entities/)
    await expect(page).toHaveURL(/originStage=chapter/)
  })

  test('Atlas keeps an independent assist workbench while navigators stay free of the old build card', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.goto('/world/1')
    await expect(page.getByTestId('atlas-assist-workbench')).toBeVisible()
    await expect(page.getByTestId('atlas-assist-open-whole-book')).toBeVisible()
    await expect(page.getByTestId('world-build-panel')).toHaveCount(0)

    await page.getByTestId('tab-entities').click()
    await expect(page.getByTestId('atlas-assist-workbench')).toBeVisible()
    await expect(page.getByTestId('world-build-panel')).toHaveCount(0)

    await page.getByTestId('tab-relationships').click()
    await expect(page.getByTestId('atlas-assist-workbench')).toBeVisible()
    await expect(page.getByTestId('world-build-panel')).toHaveCount(0)
  })
})
