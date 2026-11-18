import { type APIRequestContext, Page } from '@playwright/test'
import { NOVELS, CHAPTERS } from './data'

const BACKEND_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://localhost:8000'
export async function mockAuthRoutes(page: Page, opts: { authenticated?: boolean } = {}) {
  await page.route('**/api/auth/me', route => opts.authenticated === false
    ? route.fulfill({ status: 401, json: { detail: { code: 'not_authenticated' } } })
    : route.fulfill({ json: { id: 1, username: 'default', role: 'admin', is_active: true, preferences: null } }))
}

export async function installSession(page: Page, token: string) {
  await page.context().addCookies([{
    name: 'novwr_session',
    value: token,
    url: 'http://localhost:5173',
    httpOnly: true,
    sameSite: 'Lax',
  }])
}

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export async function getSessionToken(request: APIRequestContext): Promise<string> {
  const response = await request.post(`${BACKEND_ORIGIN}/api/auth/login`)
  if (!response.ok()) throw new Error(`Local login failed (${response.status()})`)
  return (await response.json()).access_token
}

export async function mockAllApiRoutes(page: Page) {
  // Fail-fast: abort any unmocked API request
  await page.route('**/api/**', route => route.abort('blockedbyclient'))

  await mockAuthRoutes(page)

  // Override with known routes (later routes take priority in Playwright)
  await page.route('**/api/novels', route => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: NOVELS })
    }
    return route.abort('blockedbyclient')
  })

  await page.route('**/api/novels/1', route => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: NOVELS[0] })
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204 })
    }
    return route.abort('blockedbyclient')
  })

  await page.route('**/api/novels/1/chapters/meta', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({
      json: CHAPTERS.map((c) => ({
        id: c.id,
        novel_id: c.novel_id,
        chapter_number: c.chapter_number,
        title: c.title,
        created_at: c.created_at,
      })),
    })
  })

  await page.route('**/api/novels/1/chapters', route =>
    route.fulfill({ json: CHAPTERS })
  )

  await page.route('**/api/novels/1/chapters/1', route =>
    route.fulfill({ json: CHAPTERS[0] })
  )

  await page.route('**/api/novels/1/chapters/2', route =>
    route.fulfill({ json: CHAPTERS[1] })
  )

  await page.route('**/api/novels/1/context-summaries', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({ json: [] })
  })

  // World model defaults (empty world, no bootstrap job).
  await page.route('**/api/novels/1/world/entities**', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({ json: [] })
  })

  await page.route('**/api/novels/1/world/relationships**', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({ json: [] })
  })

  await page.route('**/api/novels/1/world/systems**', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({ json: [] })
  })

  await page.route('**/api/novels/1/world/bootstrap/status', route => {
    if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
    return route.fulfill({
      status: 404,
      json: { detail: { code: 'bootstrap_job_not_found' } },
    })
  })
}

/**
 * Block only non-core external requests (CDN, analytics, avatars).
 * Use this in e2e/integration/ tests — business API goes to real backend.
 */
export async function blockExternalNoise(page: Page) {
  await page.route('**/api.dicebear.com/**', route => route.abort('blockedbyclient'))
  await page.route('**/*.analytics.*/**', route => route.abort('blockedbyclient'))
}
