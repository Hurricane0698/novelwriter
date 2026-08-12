import { test, expect } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'

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
  test('ready imported studio does not reopen empty-world onboarding on first entry', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAllApiRoutes(page)

    await mockChapterReadyStudio(page)

    await page.route('**/api/novels/1/world/bootstrap/status', route => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      return route.fulfill({
        json: {
          job_id: 9,
          novel_id: 1,
          mode: 'initial',
          initialized: true,
          status: 'completed',
          progress: { step: 5, detail: 'Done' },
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

    await page.goto('/novel/1')

    await expect(page.getByTestId('world-onboarding')).toHaveCount(0)
    await expect(page.getByTestId('studio-rail-chapters')).toBeVisible()
    await expect(page.getByRole('button', { name: /第\s*1\s*章/ })).toBeVisible()
  })

  test('Studio shows onboarding when world is empty; dismissal persists', async ({ page }) => {
    await mockAllApiRoutes(page)

    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).toBeVisible()

    await page.getByTestId('world-onboarding-dismiss').click()
    await expect(page).toHaveURL('/world/1')

    // Back to novel detail: onboarding stays dismissed (localStorage per novel).
    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).not.toBeVisible()
    await expect(page.getByTestId('studio-assistant-rail')).toBeVisible()
    await expect(page.getByTestId('world-build-panel')).toBeVisible()
    await expect(page.getByTestId('studio-rail-continuation')).toBeVisible()

    await page.getByTestId('novel-copilot-trigger').click()
    await expect(page.getByTestId('novel-copilot-drawer')).toBeVisible()
    await expect(page.getByTestId('studio-assistant-rail')).toHaveCount(0)
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
    await expect(page.getByTestId('entity-navigator').getByRole('button', { name: '测试角色' })).toBeVisible()
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

  test('bootstrap trigger stays single-flight under repeated clicks while pending', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAllApiRoutes(page)
    await mockChapterReadyStudio(page)

    let bootstrapTriggerCount = 0
    let bootstrapStatusReads = 0
    let bootstrapRunning = false

    await page.route('**/api/novels/1/world/bootstrap', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      bootstrapTriggerCount += 1
      bootstrapRunning = true
      return route.fulfill({
        json: {
          job_id: 41,
          novel_id: 1,
          mode: 'initial',
          initialized: false,
          status: 'pending',
          progress: { step: 0, detail: 'queued' },
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

    await page.route('**/api/novels/1/world/bootstrap/status', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      bootstrapStatusReads += 1
      if (!bootstrapRunning) {
        return route.fulfill({
          status: 404,
          json: { detail: { code: 'bootstrap_job_not_found' } },
        })
      }
      return route.fulfill({
        json: {
          job_id: 41,
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

    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).toBeVisible()

    const extractButton = page.getByTestId('world-onboarding-bootstrap')
    await extractButton.click()

    await expect.poll(() => bootstrapTriggerCount).toBe(1)
    await expect(page.getByTestId('studio-preparation-gate')).toBeVisible()
    await expect(page.getByText(/提取候选词|Extracting/)).toBeVisible()
    await expect(extractButton).toHaveCount(0)
    await expect.poll(() => bootstrapStatusReads).toBeGreaterThan(0)
  })

  test('failed bootstrap shows retry semantics after the pending run settles', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAllApiRoutes(page)
    await mockChapterReadyStudio(page)

    let bootstrapStatusReads = 0

    await page.route('**/api/novels/1/world/bootstrap', async (route) => {
      if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
      return route.fulfill({
        json: {
          job_id: 52,
          novel_id: 1,
          mode: 'initial',
          initialized: false,
          status: 'pending',
          progress: { step: 0, detail: 'queued' },
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

    await page.route('**/api/novels/1/world/bootstrap/status', async (route) => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      bootstrapStatusReads += 1
      if (bootstrapStatusReads === 1) {
        return route.fulfill({
          status: 404,
          json: { detail: { code: 'bootstrap_job_not_found' } },
        })
      }
      if (bootstrapStatusReads === 2) {
        return route.fulfill({
          json: {
            job_id: 52,
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
      }
      return route.fulfill({
        json: {
          job_id: 52,
          novel_id: 1,
          mode: 'initial',
          initialized: false,
          status: 'failed',
          progress: { step: 2, detail: 'Extracting...' },
          result: {
            entities_found: 0,
            relationships_found: 0,
            index_refresh_only: false,
          },
          error: 'boom',
          created_at: nowIso(),
          updated_at: nowIso(),
        },
      })
    })

    await page.goto('/novel/1')
    await expect(page.getByTestId('world-onboarding')).toBeVisible()

    await page.getByTestId('world-onboarding-bootstrap').click()

    await expect(page.getByTestId('studio-preparation-gate')).toBeVisible()
    await expect(page.getByRole('button', { name: /重新提取|Retry extraction/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /稍后处理|Defer/ })).toBeVisible()
  })

  test('pending extraction survives a browser reload as an attention gate instead of falling back to onboarding', async ({ page }) => {
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

    await expect(page.getByTestId('studio-preparation-gate')).toBeVisible()
    await expect(page.getByText(/提取候选词|Extracting/)).toBeVisible()
    await expect(page.getByTestId('world-onboarding')).toHaveCount(0)

    await page.reload()

    await expect(page.getByTestId('studio-preparation-gate')).toBeVisible()
    await expect(page.getByText(/提取候选词|Extracting/)).toBeVisible()
    await expect(page.getByTestId('world-onboarding')).toHaveCount(0)
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
