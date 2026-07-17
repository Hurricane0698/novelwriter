// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components */

import { useEffect, useState } from "react"
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom"
import { Github } from "lucide-react"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/contexts/AuthContext"
import { useUiLocale } from "@/contexts/UiLocaleContext"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useConfirmDialog } from "@/hooks/useConfirmDialog"
import { AnimatedBackground } from "@/components/layout/AnimatedBackground"
import { buildInviteAnalyticsPayload, captureHostedAttributionFromLocation, trackHostedAnalyticsEvent } from "@/lib/hostedAnalytics"
import { translateUiMessage, type UiLocale } from "@/lib/uiMessages"
import { NwButton } from "@/components/ui/nw-button"
import { ApiError, api } from "@/services/api"
import { isHostedRuntime } from "@/lib/runtimeMode"

const DEFAULT_POST_LOGIN_DESTINATION = "/library"

function resolveSafeClientRedirect(value: string | null | undefined): string {
    const candidate = (value || "").trim()
    if (!candidate || candidate.includes("\\") || candidate.includes("\u0000")) return DEFAULT_POST_LOGIN_DESTINATION

    try {
        const url = new URL(candidate, "http://novwr.local")
        if (url.origin !== "http://novwr.local") return DEFAULT_POST_LOGIN_DESTINATION
        if (!url.pathname.startsWith("/") || url.pathname.startsWith("//")) return DEFAULT_POST_LOGIN_DESTINATION
        if (url.pathname.startsWith("/login") || url.pathname.startsWith("/api")) return DEFAULT_POST_LOGIN_DESTINATION
        return `${url.pathname}${url.search}${url.hash}`
    } catch {
        return DEFAULT_POST_LOGIN_DESTINATION
    }
}

export function getPostLoginDestination(state: unknown, search = ""): string {
    if (state && typeof state === "object" && "from" in state) {
        const from = state.from
        if (typeof from === "string" && from.trim()) {
            return resolveSafeClientRedirect(from)
        }
    }

    const redirectTo = new URLSearchParams(search).get("redirect_to")
    return resolveSafeClientRedirect(redirectTo)
}

export function getOAuthErrorMessage(code: string | null, locale: UiLocale = 'zh'): string | null {
    switch (code) {
        case "github_oauth_disabled":
            return translateUiMessage(locale, 'login.oauth.disabled')
        case "github_oauth_not_configured":
            return translateUiMessage(locale, 'login.oauth.githubNotConfigured')
        case "github_oauth_state_invalid":
            return translateUiMessage(locale, 'login.oauth.stateInvalid')
        case "github_oauth_access_denied":
            return translateUiMessage(locale, 'login.oauth.accessDenied')
        case "github_oauth_signup_blocked":
            return translateUiMessage(locale, 'login.oauth.signupBlocked')
        case "github_oauth_account_disabled":
            return translateUiMessage(locale, 'login.oauth.accountDisabled')
        case "github_oauth_failed":
            return translateUiMessage(locale, 'login.oauth.failed')
        default:
            return null
    }
}

type HostedAuthMode = 'login' | 'activate'
type ActivationErrorField = 'inviteCode' | 'nickname' | 'password' | 'form'
type ActivationErrors = Partial<Record<ActivationErrorField, string>>

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null
}

function getActivationValidationField(detail: unknown): Exclude<ActivationErrorField, 'form'> | null {
    if (!Array.isArray(detail)) return null
    for (const item of detail) {
        if (!isRecord(item) || !Array.isArray(item.loc)) continue
        const loc = item.loc.map((part) => String(part))
        if (loc.includes('invite_code')) return 'inviteCode'
        if (loc.includes('nickname')) return 'nickname'
        if (loc.includes('password')) return 'password'
    }
    return null
}

export default function Login() {
    const isHosted = isHostedRuntime()
    const { locale, t } = useUiLocale()

    // Hosted mode fields
    const [hostedAuthMode, setHostedAuthMode] = useState<HostedAuthMode>('login')
    const [inviteLoginEnabled, setInviteLoginEnabled] = useState(true)
    const [inviteCode, setInviteCode] = useState("")
    const [nickname, setNickname] = useState("")
    const [hostedPassword, setHostedPassword] = useState("")
    const [activationErrors, setActivationErrors] = useState<ActivationErrors>({})

    const [isLoading, setIsLoading] = useState(false)
    const [githubLoginEnabled, setGithubLoginEnabled] = useState(false)
    const { login, activateInvite } = useAuth()
    const location = useLocation()
    const navigate = useNavigate()
    const { alert, dialogProps } = useConfirmDialog()
    const postLoginDestination = getPostLoginDestination(location.state, location.search)
    const searchParams = new URLSearchParams(location.search)
    const oauthErrorMessage = getOAuthErrorMessage(searchParams.get("oauth_error"), locale)
    const githubLoginUrl = api.getGitHubLoginUrl(postLoginDestination)

    const clearActivationError = (field: ActivationErrorField) => {
        setActivationErrors((prev) => {
            if (!prev[field] && !prev.form) return prev
            const next = { ...prev }
            delete next[field]
            if (field !== 'form') delete next.form
            return next
        })
    }

    const setActivationFieldError = (field: ActivationErrorField, message: string) => {
        setActivationErrors((prev) => ({ ...prev, [field]: message }))
    }

    useEffect(() => {
        if (!isHosted) return
        captureHostedAttributionFromLocation()
        void trackHostedAnalyticsEvent('invite_gate_view')
    }, [isHosted])

    useEffect(() => {
        if (!isHosted) return
        let cancelled = false

        api.getAuthOptions()
            .then((options) => {
                if (cancelled) return
                setInviteLoginEnabled(Boolean(options.invite_login_enabled))
                setGithubLoginEnabled(Boolean(options.github_login_enabled))
                if (!options.invite_login_enabled) {
                    setHostedAuthMode('login')
                }
                setActivationErrors({})
            })
            .catch(() => {
                if (cancelled) return
                setInviteLoginEnabled(false)
                setGithubLoginEnabled(false)
            })

        return () => {
            cancelled = true
        }
    }, [isHosted])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        setIsLoading(true)
        try {
            if (hostedAuthMode === 'activate') {
                setActivationErrors({})
                if (!inviteCode || !nickname || !hostedPassword) return
                if (hostedPassword.trim().length < 8) {
                    setActivationFieldError('password', t('login.hosted.password.minLengthError'))
                    return
                }
                void trackHostedAnalyticsEvent('invite_gate_submit', {
                    meta: { method: 'invite' },
                })
                await activateInvite(inviteCode, nickname, hostedPassword, buildInviteAnalyticsPayload())
            } else {
                if (!nickname || !hostedPassword) return
                await login(nickname, hostedPassword)
            }
            navigate(postLoginDestination, { replace: true })
        } catch (err) {
            if (err instanceof ApiError) {
                const requestIdSuffix = err.requestId ? t('login.requestIdSuffix', { requestId: err.requestId }) : ""

                if (hostedAuthMode === 'activate') {
                    if (err.status === 403) {
                        setActivationFieldError('inviteCode', `${t('login.alert.invalidInvite.description')}${requestIdSuffix}`)
                        return
                    }
                    if (err.status === 409 && err.code === 'invite_code_already_claimed') {
                        setActivationFieldError('inviteCode', `${t('login.alert.inviteClaimed.description')}${requestIdSuffix}`)
                        return
                    }
                    if (err.status === 409 && err.code === 'hosted_login_nickname_taken') {
                        setActivationFieldError('nickname', `${t('login.alert.nicknameTaken.description')}${requestIdSuffix}`)
                        return
                    }
                    if (err.status === 422) {
                        const field = getActivationValidationField(err.detail)
                        if (field === 'password') {
                            setActivationFieldError('password', `${t('login.hosted.password.minLengthError')}${requestIdSuffix}`)
                            return
                        }
                        if (field === 'nickname') {
                            setActivationFieldError('nickname', `${t('login.hosted.nickname.requiredError')}${requestIdSuffix}`)
                            return
                        }
                        if (field === 'inviteCode') {
                            setActivationFieldError('inviteCode', `${t('login.hosted.invite.requiredError')}${requestIdSuffix}`)
                            return
                        }
                        setActivationFieldError('form', `${t('login.hosted.activation.genericError')}${requestIdSuffix}`)
                        return
                    }
                    if (err.status === 503 && err.code === "hosted_user_cap_reached") {
                        setActivationFieldError('form', `${t('login.alert.signupBlocked.description')}${requestIdSuffix}`)
                        return
                    }
                    setActivationFieldError('form', `${t('login.hosted.activation.genericError')}${requestIdSuffix}`)
                    return
                } else if (err.status === 503 && err.code === "hosted_user_cap_reached") {
                    await alert({ title: t('login.alert.signupBlocked.title'), description: `${t('login.alert.signupBlocked.description')}${requestIdSuffix}` })
                } else if (err.status === 401) {
                    await alert({ title: t('login.alert.invalidCredentials.title'), description: `${t('login.alert.invalidCredentials.description')}${requestIdSuffix}` })
                } else if (err.status === 404) {
                    await alert({
                        title: t('login.alert.backend404.title'),
                        description: `${t('login.alert.backend404.description')}${requestIdSuffix}`,
                    })
                } else {
                    await alert({
                        title: t('login.alert.httpFailure.title'),
                        description: `${t('login.alert.httpFailure.description', { status: err.status })}${requestIdSuffix}`,
                    })
                }
                return
            }

            if (hostedAuthMode === 'activate') {
                setActivationFieldError('form', t('login.hosted.activation.networkError'))
            } else {
                await alert({
                    title: t('login.alert.network.title'),
                    description: t('login.alert.network.description'),
                })
            }
        } finally {
            setIsLoading(false)
        }
    }

    if (!isHosted) return <Navigate to="/" replace />

    return (
        <div className="min-h-screen grid items-center justify-center relative overflow-hidden">
            <AnimatedBackground />

            <div className="w-[420px] z-10 rounded-[20px] p-10 bg-[var(--nw-glass-bg)] backdrop-blur-[24px] border border-[var(--nw-glass-border)] flex flex-col gap-8">
                {/* Header */}
                <div className="flex flex-col gap-3 w-full">
                    <span className="font-mono text-[28px] font-bold text-foreground">NovWr</span>
                    <span className="font-sans text-[15px] text-muted-foreground">
                        {t(githubLoginEnabled ? 'login.header.hosted' : 'login.header.hostedInviteOnly')}
                    </span>
                </div>

                {oauthErrorMessage ? (
                    <div className="rounded-xl border border-[hsl(var(--color-danger)/0.28)] bg-[hsl(var(--color-danger)/0.10)] px-4 py-3 text-sm text-foreground">
                        {oauthErrorMessage}
                    </div>
                ) : null}

                {/* Form */}
                <form onSubmit={handleSubmit} className="flex flex-col gap-5 w-full" data-testid="login-form">
                    <>
                            {githubLoginEnabled ? (
                                <>
                                    <NwButton
                                        asChild
                                        variant="glass"
                                        className="h-11 w-full rounded-xl border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.5)] text-sm font-medium"
                                    >
                                        <a href={githubLoginUrl} data-testid="login-github-link">
                                            <Github className="h-4 w-4" />
                                            {t('login.github.button')}
                                        </a>
                                    </NwButton>

                                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                        <div className="h-px flex-1 bg-[var(--nw-glass-border)]" />
                                        <span>{t('login.invite.or')}</span>
                                        <div className="h-px flex-1 bg-[var(--nw-glass-border)]" />
                                    </div>
                                </>
                            ) : null}

                            <div className="grid grid-cols-2 gap-2">
                                <NwButton
                                    type="button"
                                    variant={hostedAuthMode === 'login' ? 'accent' : 'glass'}
                                    className="h-10 rounded-xl text-sm"
                                    aria-pressed={hostedAuthMode === 'login'}
                                    onClick={() => {
                                        setHostedAuthMode('login')
                                        setActivationErrors({})
                                    }}
                                    data-testid="hosted-mode-login"
                                >
                                    {t('login.hosted.mode.login')}
                                </NwButton>
                                <NwButton
                                    type="button"
                                    variant={hostedAuthMode === 'activate' ? 'accent' : 'glass'}
                                    className="h-10 rounded-xl text-sm"
                                    aria-pressed={hostedAuthMode === 'activate'}
                                    onClick={() => {
                                        setHostedAuthMode('activate')
                                        setActivationErrors({})
                                    }}
                                    disabled={!inviteLoginEnabled}
                                    data-testid="hosted-mode-activate"
                                >
                                    {t('login.hosted.mode.activate')}
                                </NwButton>
                            </div>

                            <p className="text-xs leading-5 text-muted-foreground">
                                {hostedAuthMode === 'activate'
                                    ? t('login.hosted.activateHint')
                                    : t('login.hosted.loginHint')}
                            </p>

                            {hostedAuthMode === 'activate' && activationErrors.form ? (
                                <div
                                    className="rounded-lg border border-[hsl(var(--color-danger)/0.28)] bg-[hsl(var(--color-danger)/0.10)] px-3 py-2 text-xs leading-5 text-[hsl(var(--color-danger))]"
                                    data-testid="activation-form-error"
                                >
                                    {activationErrors.form}
                                </div>
                            ) : null}

                            {hostedAuthMode === 'activate' ? (
                                <div className="flex flex-col gap-1.5 w-full">
                                    <label className="text-sm font-medium leading-none" htmlFor="invite-code">
                                        {t('login.invite.code.label')}
                                    </label>
                                    <Input
                                        id="invite-code"
                                        type="text"
                                        value={inviteCode}
                                        onChange={(e) => {
                                            setInviteCode(e.target.value)
                                            clearActivationError('inviteCode')
                                        }}
                                        placeholder={t('login.invite.code.placeholder')}
                                        className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                        aria-invalid={activationErrors.inviteCode ? true : undefined}
                                        required
                                    />
                                    {activationErrors.inviteCode ? (
                                        <div
                                            className="rounded-lg border border-[hsl(var(--color-danger)/0.24)] bg-[hsl(var(--color-danger)/0.08)] px-3 py-2 text-xs leading-5 text-[hsl(var(--color-danger))]"
                                            data-testid="activation-invite-error"
                                        >
                                            {activationErrors.inviteCode}
                                        </div>
                                    ) : null}
                                </div>
                            ) : null}

                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="nickname">
                                    {t('login.invite.nickname.label')}
                                </label>
                                <Input
                                    id="nickname"
                                    type="text"
                                    value={nickname}
                                    onChange={(e) => {
                                        setNickname(e.target.value)
                                        if (hostedAuthMode === 'activate') clearActivationError('nickname')
                                    }}
                                    placeholder={
                                        hostedAuthMode === 'activate'
                                            ? t('login.invite.nickname.placeholder')
                                            : t('login.hosted.nickname.placeholder')
                                    }
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    aria-invalid={hostedAuthMode === 'activate' && activationErrors.nickname ? true : undefined}
                                    required
                                />
                                {hostedAuthMode === 'activate' && activationErrors.nickname ? (
                                    <div
                                        className="rounded-lg border border-[hsl(var(--color-danger)/0.24)] bg-[hsl(var(--color-danger)/0.08)] px-3 py-2 text-xs leading-5 text-[hsl(var(--color-danger))]"
                                        data-testid="activation-nickname-error"
                                    >
                                        {activationErrors.nickname}
                                    </div>
                                ) : null}
                            </div>

                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="hosted-password">
                                    {t('login.password.label')}
                                </label>
                                <Input
                                    id="hosted-password"
                                    type="password"
                                    value={hostedPassword}
                                    onChange={(e) => {
                                        setHostedPassword(e.target.value)
                                        if (hostedAuthMode === 'activate') clearActivationError('password')
                                    }}
                                    placeholder={
                                        hostedAuthMode === 'activate'
                                            ? t('login.hosted.password.activatePlaceholder')
                                            : t('login.hosted.password.loginPlaceholder')
                                    }
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    minLength={hostedAuthMode === 'activate' ? 8 : undefined}
                                    aria-invalid={hostedAuthMode === 'activate' && activationErrors.password ? true : undefined}
                                    required
                                />
                                {hostedAuthMode === 'activate' ? (
                                    <p className="text-xs leading-5 text-muted-foreground">
                                        {t('login.hosted.password.hint')}
                                    </p>
                                ) : null}
                                {hostedAuthMode === 'activate' && activationErrors.password ? (
                                    <div
                                        className="rounded-lg border border-[hsl(var(--color-danger)/0.24)] bg-[hsl(var(--color-danger)/0.08)] px-3 py-2 text-xs leading-5 text-[hsl(var(--color-danger))]"
                                        data-testid="activation-password-error"
                                    >
                                        {activationErrors.password}
                                    </div>
                                ) : null}
                            </div>
                    </>

                    <NwButton
                        type="submit"
                        disabled={isLoading}
                        data-testid="login-submit"
                        variant="accent"
                        className="w-full h-11 rounded-xl font-medium text-sm shadow-[0_0_20px_hsl(var(--accent)/0.40)] transition-[background-color,box-shadow] hover:shadow-[0_0_28px_hsl(var(--accent)/0.55)]"
                    >
                        {isLoading
                            ? t('login.submit.loading')
                            : hostedAuthMode === 'activate'
                                ? t('login.submit.activate')
                                : t('login.submit.hostedLogin')}
                    </NwButton>

                    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-1 text-xs text-muted-foreground">
                        <Link to="/terms" className="transition-colors hover:text-foreground">{t('footer.link.terms')}</Link>
                        <Link to="/privacy" className="transition-colors hover:text-foreground">{t('footer.link.privacy')}</Link>
                        <Link to="/copyright" className="transition-colors hover:text-foreground">{t('footer.link.copyright')}</Link>
                    </div>
                </form>
            </div>
            <ConfirmDialog {...dialogProps} />
        </div>
    )
}
