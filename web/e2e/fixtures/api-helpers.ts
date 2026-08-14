import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { type APIRequestContext, Page } from '@playwright/test'
import { NOVELS, CHAPTERS } from './data'

const BACKEND_ORIGIN = 'http://localhost:8000'
const FRONTEND_ORIGIN = 'http://localhost:5173'
const SESSION_COOKIE_NAME = 'novwr_session'
const UPLOAD_CONSENT_VERSION = '2026-03-06'
const DEFAULT_PASSWORD = 'password123!'

export type LoginOptions = {
  inviteCode?: string
  nickname?: string
  username?: string
  password?: string
  profile?: string
  scope?: string
}

type DeployMode = 'hosted' | 'selfhost'

type ResolvedLoginOptions = {
  inviteCode: string | null
  nickname: string
  username: string
  password: string
}

export type ApiSession = {
  accessToken: string
  deployMode: DeployMode
  nickname: string
  username: string
}

const MOCK_USER = {
  id: 1,
  username: 'test',
  nickname: 'test',
  role: 'user',
  is_active: true,
  generation_quota: 5,
  feedback_submitted: false,
}

export async function mockAuthRoutes(page: Page, opts: { authenticated?: boolean } = {}) {
  let authenticated = opts.authenticated ?? true

  await page.route('**/api/auth/me', (route) => {
    if (!authenticated) {
      return route.fulfill({ status: 401, json: { detail: { code: 'not_authenticated' } } })
    }
    return route.fulfill({ json: MOCK_USER })
  })

  await page.route('**/api/auth/login', (route) => {
    if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
    authenticated = true
    return route.fulfill({ json: { access_token: 'mock_token', token_type: 'bearer' } })
  })

  await page.route('**/api/auth/invite', (route) => {
    if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
    authenticated = true
    return route.fulfill({ json: { access_token: 'mock_token', token_type: 'bearer' } })
  })

  await page.route('**/api/auth/logout', (route) => {
    if (route.request().method() !== 'POST') return route.abort('blockedbyclient')
    authenticated = false
    return route.fulfill({ status: 204 })
  })

  await page.route('**/api/auth/quota', (route) => {
    if (!authenticated) {
      return route.fulfill({ status: 401, json: { detail: { code: 'not_authenticated' } } })
    }
    return route.fulfill({ json: { generation_quota: MOCK_USER.generation_quota, feedback_submitted: false } })
  })
}

export async function installSession(page: Page, token: string, userId?: number | string) {
  await page.context().addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: token,
      url: FRONTEND_ORIGIN,
      httpOnly: true,
      sameSite: 'Lax',
    },
  ])

  if (userId !== undefined && userId !== null) {
    await page.addInitScript(({ consentVersion, uid }) => {
      localStorage.setItem(`novwr_upload_consent_${consentVersion}:anonymous`, '1')
      localStorage.setItem(`novwr_upload_consent_${consentVersion}:${uid}`, '1')
    }, { consentVersion: UPLOAD_CONSENT_VERSION, uid: String(userId) })
  }
}


let dotenvText: string | null | undefined

function readE2EEnvValue(...names: string[]): string | null {
  for (const name of names) {
    const fromProcess = process.env[name]?.trim()
    if (fromProcess) return fromProcess
  }

  if (dotenvText === undefined) {
    try {
      const here = path.dirname(fileURLToPath(import.meta.url))
      const envPath = path.resolve(here, '../../../.env')
      dotenvText = fs.readFileSync(envPath, 'utf-8')
    } catch {
      dotenvText = null
    }
  }

  if (!dotenvText) return null

  for (const name of names) {
    const match = dotenvText.match(new RegExp(`^${name}=(.*)$`, 'm'))
    const value = match?.[1]?.trim().replace(/^['"]|['"]$/g, '')
    if (value) return value
  }

  return null
}

function readInviteCodes(): string[] {
  const explicit = readE2EEnvValue('E2E_INVITE_CODE')
  if (explicit) return [explicit]

  const hostedInviteCodesRaw = readE2EEnvValue('HOSTED_INVITE_CODES')
  if (!hostedInviteCodesRaw) return []

  try {
    const parsed = JSON.parse(hostedInviteCodesRaw) as Array<{ code?: unknown }> | null
    return Array.isArray(parsed)
      ? parsed
          .map((item) => (typeof item?.code === 'string' ? item.code.trim() : ''))
          .filter(Boolean)
      : []
  } catch {
    return []
  }
}

export function readInviteCode(): string | null {
  return readInviteCodes()[0] ?? null
}

export function getDeployMode(): DeployMode {
  return (readE2EEnvValue('DEPLOY_MODE') ?? 'selfhost').toLowerCase() === 'hosted'
    ? 'hosted'
    : 'selfhost'
}

function normalizeScope(scope?: string): string {
  const normalized = (scope ?? 'shared')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')

  return normalized || 'shared'
}

function normalizeProfile(profile?: string): string | null {
  const normalized = (profile ?? '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')

  return normalized || null
}

function pickInviteCodeForScope(scope: string): string | null {
  const codes = readInviteCodes()
  if (codes.length === 0) return null
  if (codes.length === 1) return codes[0]

  let hash = 0
  for (const ch of scope) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  }
  return codes[hash % codes.length] ?? codes[0]
}

function resolveLoginOptions(options: LoginOptions = {}): ResolvedLoginOptions {
  const deployMode = getDeployMode()
  const scope = normalizeScope(options.scope)
  const profile = normalizeProfile(options.profile ?? readE2EEnvValue('E2E_HOSTED_PROFILE'))

  if (deployMode === 'hosted') {
    const profiledInviteCode = profile ? readE2EEnvValue(`E2E_HOSTED_${profile}_INVITE_CODE`) : null
    const profiledNickname = profile ? readE2EEnvValue(`E2E_HOSTED_${profile}_NICKNAME`) : null
    const profiledPassword = profile ? readE2EEnvValue(`E2E_HOSTED_${profile}_PASSWORD`) : null
    const profiledUsername = profile ? readE2EEnvValue(`E2E_HOSTED_${profile}_USERNAME`) : null
    const inviteCode = options.inviteCode ?? pickInviteCodeForScope(scope)
    const hasMultipleInviteCodes = readInviteCodes().length > 1
    const hostedNickname = options.nickname
      ?? profiledNickname
      ?? (hasMultipleInviteCodes ? `e2e_${scope}` : readE2EEnvValue('E2E_HOSTED_NICKNAME') ?? 'e2e_hosted')
    const hostedPassword = options.password
      ?? profiledPassword
      ?? readE2EEnvValue('E2E_HOSTED_PASSWORD')
      ?? DEFAULT_PASSWORD
    return {
      inviteCode: options.inviteCode ?? profiledInviteCode ?? inviteCode,
      nickname: hostedNickname,
      username: options.username ?? profiledUsername ?? hostedNickname,
      password: hostedPassword,
    }
  }

  return {
    inviteCode: options.inviteCode ?? readInviteCode(),
    nickname: options.nickname ?? `e2e_${scope}`,
    username: options.username ?? `e2e_${scope}`,
    password: options.password ?? DEFAULT_PASSWORD,
  }
}

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export async function createApiSession(
  request: APIRequestContext,
  options: LoginOptions = {},
): Promise<ApiSession> {
  const deployMode = getDeployMode()
  const login = resolveLoginOptions(options)

  if (deployMode === 'hosted' && !login.inviteCode) {
    throw new Error('Hosted login requires HOSTED_INVITE_CODES or E2E_INVITE_CODE (set env or repo-root .env).')
  }

  let hostedErrorBody: string | null = null

  const response = deployMode === 'hosted'
    ? await (async () => {
        const loginResponse = await request.post(`${BACKEND_ORIGIN}/api/auth/login`, {
          form: {
            username: login.nickname,
            password: login.password,
          },
        })
        if (loginResponse.ok() || loginResponse.status() !== 401) {
          return loginResponse
        }

        const inviteResponse = await request.post(`${BACKEND_ORIGIN}/api/auth/invite`, {
          data: {
            invite_code: login.inviteCode,
            nickname: login.nickname,
            password: login.password,
          },
        })

        if (inviteResponse.ok()) {
          return inviteResponse
        }

        const inviteText = await inviteResponse.text()
        if (inviteResponse.status() === 409 && inviteText.includes('invite_code_already_claimed')) {
          const retryLoginResponse = await request.post(`${BACKEND_ORIGIN}/api/auth/login`, {
            form: {
              username: login.nickname,
              password: login.password,
            },
          })
          if (retryLoginResponse.ok()) {
            return retryLoginResponse
          }
          hostedErrorBody = await retryLoginResponse.text()
          return retryLoginResponse
        }

        hostedErrorBody = inviteText
        return inviteResponse
      })()
    : await request.post(`${BACKEND_ORIGIN}/api/auth/login`, {
        form: {
          username: login.username,
          password: login.password,
        },
      })

  if (!response.ok()) {
    const body = hostedErrorBody ?? await response.text()
    throw new Error(`E2E auth failed (${deployMode}): ${response.status()} ${body}`)
  }

  const payload = (await response.json()) as { access_token: string }
  return {
    accessToken: payload.access_token,
    deployMode,
    nickname: login.nickname,
    username: login.username,
  }
}

async function waitForPostLoginNavigation(page: Page, timeoutMs = 4_000): Promise<boolean> {
  try {
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: timeoutMs })
    return true
  } catch {
    return false
  }
}

async function dismissLoginAlertIfPresent(page: Page): Promise<void> {
  const dismissButton = page.getByRole('button', { name: /知道了|Got it|确认|Confirm/ }).first()
  if (await dismissButton.isVisible().catch(() => false)) {
    await dismissButton.click()
  }
}

export async function submitLoginForm(page: Page, options: LoginOptions = {}) {
  await page.getByTestId('login-form').waitFor({ state: 'visible', timeout: 15_000 })

  const login = resolveLoginOptions(options)

  if (await page.locator('#username').count()) {
    await page.getByLabel('用户名').fill(login.username)
    await page.getByLabel('密码').fill(login.password)
    await page.getByTestId('login-submit').click()
    return
  }

  if (!login.inviteCode) {
    throw new Error('Hosted login requires HOSTED_INVITE_CODES or E2E_INVITE_CODE (set env or repo-root .env).')
  }

  if (await page.getByTestId('hosted-mode-login').count()) {
    await page.getByTestId('hosted-mode-login').click()
  }
  await page.locator('#nickname').fill(login.nickname)
  await page.locator('#hosted-password').fill(login.password)
  await page.getByTestId('login-submit').click()

  if (await waitForPostLoginNavigation(page, 2_500)) {
    return
  }

  await dismissLoginAlertIfPresent(page)

  if (await page.getByTestId('hosted-mode-activate').count()) {
    await page.getByTestId('hosted-mode-activate').click()
  }

  if (await page.locator('#invite-code').count()) {
    if (!login.inviteCode) {
      throw new Error('Hosted login requires HOSTED_INVITE_CODES or E2E_INVITE_CODE (set env or repo-root .env).')
    }

    await page.locator('#invite-code').fill(login.inviteCode)
    await page.locator('#nickname').fill(login.nickname)
    await page.locator('#hosted-password').fill(login.password)
    await page.getByTestId('login-submit').click()
    return
  }

  throw new Error('Hosted activation form was not available after login fallback failed.')
}


export async function ensureProductAccess(page: Page, options: LoginOptions = {}) {
  if (getDeployMode() === 'selfhost') {
    await page.goto('/library')
    await page.waitForURL(/\/library$/, { timeout: 15_000 })
    return
  }

  await page.goto('/login')
  await submitLoginForm(page, options)
  await page.waitForURL(/\/library$/, { timeout: 15_000 })
}

/**
 * Mock all API routes with default data.
 * Unmocked routes will abort — use this in e2e/mock/ tests only.
 */
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
