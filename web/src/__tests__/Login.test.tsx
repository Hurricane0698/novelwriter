import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'

const {
  loginMock,
  activateInviteMock,
  alertMock,
  getGitHubLoginUrlMock,
  getAuthOptionsMock,
} = vi.hoisted(() => ({
  loginMock: vi.fn(),
  activateInviteMock: vi.fn(),
  alertMock: vi.fn(),
  getGitHubLoginUrlMock: vi.fn((redirectTo: string) => `/api/auth/github/start?redirect_to=${encodeURIComponent(redirectTo)}`),
  getAuthOptionsMock: vi.fn(),
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: loginMock,
    activateInvite: activateInviteMock,
  }),
}))

vi.mock('@/hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({
    alert: alertMock,
    dialogProps: {},
  }),
}))

vi.mock('@/components/ui/confirm-dialog', () => ({
  ConfirmDialog: () => null,
}))

vi.mock('@/components/layout/AnimatedBackground', () => ({
  AnimatedBackground: () => <div data-testid="animated-background" />,
}))

vi.mock('@/services/api', () => ({
  api: {
    login: loginMock,
    activateInvite: activateInviteMock,
    getAuthOptions: getAuthOptionsMock,
    getGitHubLoginUrl: getGitHubLoginUrlMock,
  },
  ApiError: class ApiError extends Error {
    status = 500
    code?: string
    requestId?: string
  },
}))

import Login, { getOAuthErrorMessage, getPostLoginDestination } from '@/pages/Login'
import { ApiError } from '@/services/api'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{location.pathname}</div>
}

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
    getAuthOptionsMock.mockResolvedValue({
      deploy_mode: 'hosted',
      invite_login_enabled: true,
      github_login_enabled: true,
    })
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('keeps only safe post-login destinations', () => {
    expect(getPostLoginDestination({ from: '/novel/1?stage=write' })).toBe('/novel/1?stage=write')
    expect(getPostLoginDestination({ from: 'https://evil.example/phish' })).toBe('/library')
    expect(getPostLoginDestination({ from: '//evil.example/phish' })).toBe('/library')
    expect(getPostLoginDestination(null, '?redirect_to=%2Fworld%2F7')).toBe('/world/7')
    expect(getPostLoginDestination(null, '?redirect_to=https%3A%2F%2Fevil.example')).toBe('/library')
  })

  it.each(['desktop', 'selfhost'] as const)('redirects the local %s login route back to the landing page', async (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)

    render(
      <UiLocaleProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    expect(await screen.findByTestId('location-path')).toHaveTextContent('/')
    expect(getAuthOptionsMock).not.toHaveBeenCalled()
    expect(screen.queryByTestId('login-form')).toBeNull()
  })

  it('maps GitHub OAuth callback errors to user-facing copy', () => {
    expect(getOAuthErrorMessage('github_oauth_state_invalid')).toContain('登录状态已失效')
    expect(getOAuthErrorMessage('github_oauth_disabled')).toContain('GitHub 登录')
    expect(getOAuthErrorMessage('github_oauth_signup_blocked')).toContain('暂不接受新的 GitHub 注册')
    expect(getOAuthErrorMessage('github_oauth_state_invalid', 'en')).toContain('login state expired')
    expect(getOAuthErrorMessage(null)).toBeNull()
  })

  it('renders the hosted GitHub login entry and preserves the safe redirect target', async () => {
    render(
      <UiLocaleProvider>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/login',
              search: '?oauth_error=github_oauth_state_invalid&redirect_to=%2Fnovel%2F1',
            },
          ]}
        >
          <Login />
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    expect(screen.getByText('登录状态已失效，请重新点击 GitHub 登录。')).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('login-github-link')).toBeVisible()
    })
    expect(screen.getByTestId('login-github-link')).toHaveAttribute(
      'href',
      '/api/auth/github/start?redirect_to=%2Fnovel%2F1',
    )
    expect(getGitHubLoginUrlMock).toHaveBeenCalledWith('/novel/1')
    expect(screen.getByTestId('hosted-mode-login')).toBeVisible()
    expect(screen.getByTestId('hosted-mode-activate')).toBeVisible()
    expect(screen.queryByLabelText('邀请码')).toBeNull()
  })

  it('renders English login copy when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    render(
      <UiLocaleProvider>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/login',
              search: '?oauth_error=github_oauth_state_invalid',
            },
          ]}
        >
          <Login />
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    expect(screen.getByText('Your login state expired. Please click GitHub sign-in again.')).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('login-github-link')).toBeVisible()
    })
    expect(screen.getByPlaceholderText('Enter the nickname you activated with')).toBeVisible()
    expect(screen.getByTestId('login-submit')).toHaveTextContent('Log in')

    fireEvent.click(screen.getByTestId('hosted-mode-activate'))
    expect(screen.getByLabelText('Invite code')).toBeVisible()
    expect(screen.getByText('Use at least 8 characters. After activation, you will sign in with nickname and password.')).toBeVisible()
    expect(screen.getByTestId('login-submit')).toHaveTextContent('Activate and enter')
  })

  it('shows an inline password error for short activation passwords instead of opening a dialog', async () => {
    render(
      <UiLocaleProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Login />
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('hosted-mode-activate')).toBeVisible()
    })

    fireEvent.click(screen.getByTestId('hosted-mode-activate'))
    fireEvent.change(screen.getByLabelText('邀请码'), { target: { value: 'TEST-CODE-123' } })
    fireEvent.change(screen.getByLabelText('昵称'), { target: { value: '测试用户' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: '1234567' } })
    fireEvent.submit(screen.getByTestId('login-form'))

    expect(screen.getByTestId('activation-password-error')).toHaveTextContent('密码必须至少填写 8 位。')
    expect(activateInviteMock).not.toHaveBeenCalled()
    expect(alertMock).not.toHaveBeenCalled()
  })

  it('maps backend 422 activation validation errors into inline field banners', async () => {
    activateInviteMock.mockRejectedValue(
      Object.assign(new ApiError('HTTP 422'), {
        status: 422,
        detail: [{ loc: ['body', 'password'], type: 'string_too_short' }],
        requestId: 'req_422_password',
      }),
    )

    render(
      <UiLocaleProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Login />
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('hosted-mode-activate')).toBeVisible()
    })

    fireEvent.click(screen.getByTestId('hosted-mode-activate'))
    fireEvent.change(screen.getByLabelText('邀请码'), { target: { value: 'TEST-CODE-123' } })
    fireEvent.change(screen.getByLabelText('昵称'), { target: { value: '测试用户' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: '12345678' } })
    fireEvent.submit(screen.getByTestId('login-form'))

    await waitFor(() => {
      expect(screen.getByTestId('activation-password-error')).toHaveTextContent('密码必须至少填写 8 位。')
    })
    expect(screen.getByTestId('activation-password-error')).toHaveTextContent('Request ID: req_422_password')
    expect(alertMock).not.toHaveBeenCalled()
  })

  it('defaults to invite-only hosted login when GitHub is disabled at runtime', async () => {
    getAuthOptionsMock.mockResolvedValue({
      deploy_mode: 'hosted',
      invite_login_enabled: true,
      github_login_enabled: false,
    })

    render(
      <UiLocaleProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Login />
        </MemoryRouter>
      </UiLocaleProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('首次使用请用邀请码激活；之后用昵称和密码登录')).toBeVisible()
    })
    expect(screen.queryByTestId('login-github-link')).toBeNull()
    expect(screen.getByText('如果你已经激活过账号，请直接用昵称和密码登录。')).toBeVisible()
    fireEvent.click(screen.getByTestId('hosted-mode-activate'))
    expect(screen.getByLabelText('邀请码')).toBeVisible()
  })
})
