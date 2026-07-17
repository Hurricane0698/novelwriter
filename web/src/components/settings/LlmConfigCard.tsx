import { useState, type ChangeEventHandler, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useUiLocale } from "@/contexts/UiLocaleContext"
import { useConfirmDialog } from "@/hooks/useConfirmDialog"
import { getLlmApiErrorMessage, getLlmConfigWarning } from "@/lib/llmErrorMessages"
import {
    clearSelfhostLlmConfig,
    getSelfhostLlmConfig,
    setSelfhostLlmConfig,
} from "@/lib/selfhostLlmConfigStore"
import { getRuntimeMode } from "@/lib/runtimeMode"
import { api, ApiError, type LlmConfigResponse, type LlmProbeResponse } from "@/services/api"
import { translateUiMessage, type UiLocale } from "@/lib/uiMessages"

const DESKTOP_LLM_CONFIG_QUERY_KEY = ['llm', 'desktop-config'] as const

type ResultState = { ok: boolean; message: string } | null

type DesktopConfigDraft = {
    baseUrl: string
    apiKey: string
    model: string
}

type ConfigInputProps = {
    id: string
    label: string
    type?: 'text' | 'password'
    value: string
    onChange: ChangeEventHandler<HTMLInputElement>
    onBlur?: () => void
    placeholder: string
    disabled?: boolean
    footer?: ReactNode
}

function ConfigInput({
    id,
    label,
    type = 'text',
    value,
    onChange,
    onBlur,
    placeholder,
    disabled,
    footer,
}: ConfigInputProps) {
    return (
        <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor={id}>{label}</label>
            <input
                id={id}
                type={type}
                value={value}
                onChange={onChange}
                onBlur={onBlur}
                placeholder={placeholder}
                disabled={disabled}
                className="h-10 rounded-lg border border-[var(--nw-glass-border)] bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
            />
            {footer}
        </div>
    )
}

function ConfigResult({ result }: { result: ResultState }) {
    if (!result) return null
    return (
        <div
            data-testid="llm-config-result"
            className={`text-sm px-3 py-2 rounded-lg ${
                result.ok ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"
            }`}
        >
            {result.message}
        </div>
    )
}

function ConfigWarning({ message }: { message: string | null }) {
    if (!message) return null
    return (
        <div className="rounded-lg border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.10)] px-3 py-2 text-sm text-[hsl(var(--color-warning))]">
            {message}
        </div>
    )
}

function formatLlmError(error: unknown, locale: UiLocale, fallback: string): string {
    if (error instanceof ApiError) {
        return getLlmApiErrorMessage(error, locale)
            ?? translateUiMessage(locale, 'llm.result.httpFailed', { status: error.status })
    }
    return error instanceof Error ? error.message : fallback
}

function formatLlmProbeResult(response: LlmProbeResponse, locale: UiLocale): ResultState {
    switch (response.code) {
        case 'llm_probe_compatible':
            return {
                ok: true,
                message: translateUiMessage(locale, 'llm.result.successFallback', {
                    latencyMs: response.latency_ms,
                }),
            }
        case 'llm_probe_connection_failed':
            return {
                ok: false,
                message: translateUiMessage(locale, 'llm.result.providerConnectionFailed'),
            }
        case 'llm_probe_capability_mismatch':
            if (!response.capabilities.stream && !response.capabilities.json_mode) {
                return {
                    ok: false,
                    message: translateUiMessage(locale, 'llm.result.missingStreamAndJsonCapabilities'),
                }
            }
            if (!response.capabilities.stream) {
                return {
                    ok: false,
                    message: translateUiMessage(locale, 'llm.result.missingStreamCapability'),
                }
            }
            return {
                ok: false,
                message: translateUiMessage(locale, 'llm.result.missingJsonCapability'),
            }
    }
}

function HostedLlmConfigCard() {
    const { t } = useUiLocale()
    return (
        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6">
            <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-white/5 px-4 py-3.5 text-sm leading-6 text-muted-foreground">
                {t('llm.notice.hosted')}
            </div>
        </div>
    )
}

function SelfhostLlmConfigCard() {
    const { locale, t } = useUiLocale()
    const initialConfig = getSelfhostLlmConfig()
    const [baseUrl, setBaseUrl] = useState(initialConfig.baseUrl)
    const [apiKey, setApiKey] = useState(initialConfig.apiKey)
    const [model, setModel] = useState(initialConfig.model)
    const [testing, setTesting] = useState(false)
    const [result, setResult] = useState<ResultState>(null)
    const busy = testing

    const save = () => {
        setSelfhostLlmConfig({
            baseUrl,
            apiKey,
            model,
        })
    }
    const partialConfigWarning = getLlmConfigWarning({
        baseUrl,
        apiKey,
        model,
    }, locale)

    const testConnection = async () => {
        save()
        setTesting(true)
        setResult(null)
        try {
            const response = await api.testLlmConnection()
            setResult(formatLlmProbeResult(response, locale))
        } catch (error) {
            setResult({ ok: false, message: formatLlmError(error, locale, t('llm.result.connectionFailed')) })
        } finally {
            setTesting(false)
        }
    }

    const clear = () => {
        clearSelfhostLlmConfig()
        setBaseUrl("")
        setApiKey("")
        setModel("")
        setResult(null)
    }

    return (
        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6 flex flex-col gap-5">
            <p className="text-sm leading-6 text-muted-foreground">{t('llm.notice.selfhost')}</p>
            <ConfigWarning message={partialConfigWarning} />
            <ConfigInput
                id="llm-base-url"
                label={t('llm.label.baseUrl')}
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                onBlur={save}
                placeholder="https://api.openai.com/v1"
                disabled={busy}
            />
            <ConfigInput
                id="llm-api-key"
                label={t('llm.label.apiKey')}
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                onBlur={save}
                placeholder="sk-..."
                disabled={busy}
            />
            <ConfigInput
                id="llm-model"
                label={t('llm.label.model')}
                value={model}
                onChange={(event) => setModel(event.target.value)}
                onBlur={save}
                placeholder="gpt-4o-mini"
                disabled={busy}
            />
            <button
                type="button"
                onClick={testConnection}
                disabled={busy || !baseUrl || !apiKey || !model}
                data-testid="llm-config-test"
                className="flex items-center justify-center h-10 rounded-[10px] border border-accent/25 text-accent hover:bg-accent/8 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
            >
                {testing ? t('llm.button.testing') : t('llm.button.test')}
            </button>
            <button
                type="button"
                onClick={clear}
                disabled={busy}
                data-testid="llm-config-clear"
                className="flex items-center justify-center h-10 rounded-[10px] border border-[var(--nw-glass-border)] text-sm font-medium text-muted-foreground transition-colors hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed"
            >
                {t('llm.button.clearSelfhost')}
            </button>
            <ConfigResult result={result} />
        </div>
    )
}

function emptyDesktopConfig(): LlmConfigResponse {
    return {
        configured: false,
        base_url: '',
        model: '',
        api_key_configured: false,
    }
}

function DesktopLlmConfigCard() {
    const { locale, t } = useUiLocale()
    const queryClient = useQueryClient()
    const { confirm, dialogProps } = useConfirmDialog()
    const [draft, setDraft] = useState<DesktopConfigDraft | null>(null)
    const [result, setResult] = useState<ResultState>(null)

    const configQuery = useQuery({
        queryKey: DESKTOP_LLM_CONFIG_QUERY_KEY,
        queryFn: api.getLlmConfig,
        retry: false,
    })
    const saveMutation = useMutation({ mutationFn: api.updateLlmConfig })
    const clearMutation = useMutation({ mutationFn: api.clearLlmConfig })
    const testMutation = useMutation({ mutationFn: api.testLlmConnection })

    const persistedConfig = configQuery.data ?? emptyDesktopConfig()
    const baseUrl = draft?.baseUrl ?? persistedConfig.base_url
    const apiKey = draft?.apiKey ?? ''
    const model = draft?.model ?? persistedConfig.model
    const dirty = draft !== null
    const apiKeyConfigured = persistedConfig.api_key_configured

    const effectiveApiKey = apiKey || (apiKeyConfigured ? '__configured__' : '')
    const partialConfigWarning = getLlmConfigWarning({
        baseUrl,
        apiKey: effectiveApiKey,
        model,
    }, locale)
    const completeDraft = Boolean(baseUrl && model && effectiveApiKey)

    const edit = (field: keyof DesktopConfigDraft, value: string) => {
        setDraft((current) => ({
            baseUrl: current?.baseUrl ?? persistedConfig.base_url,
            apiKey: current?.apiKey ?? '',
            model: current?.model ?? persistedConfig.model,
            [field]: value,
        }))
        setResult(null)
    }

    const save = async () => {
        if (!draft) return
        setResult(null)
        try {
            const nextApiKey = draft.apiKey
            const saved = await saveMutation.mutateAsync({
                base_url: draft.baseUrl,
                model: draft.model,
                ...(nextApiKey ? { api_key: nextApiKey } : {}),
            })
            queryClient.setQueryData(DESKTOP_LLM_CONFIG_QUERY_KEY, saved)
            setDraft(null)
            setResult({ ok: true, message: t('llm.result.saved') })
        } catch (error) {
            setResult({ ok: false, message: formatLlmError(error, locale, t('llm.result.connectionFailed')) })
        }
    }

    const testConnection = async () => {
        setResult(null)
        try {
            const response = await testMutation.mutateAsync()
            setResult(formatLlmProbeResult(response, locale))
        } catch (error) {
            setResult({ ok: false, message: formatLlmError(error, locale, t('llm.result.connectionFailed')) })
        }
    }

    const clear = async () => {
        const confirmed = await confirm({
            title: t('llm.confirm.clearTitle'),
            description: t('llm.confirm.clearDescription'),
            confirmText: t('llm.confirm.clearAction'),
            tone: 'destructive',
        })
        if (!confirmed) return
        setResult(null)
        try {
            await clearMutation.mutateAsync()
            queryClient.setQueryData(DESKTOP_LLM_CONFIG_QUERY_KEY, emptyDesktopConfig())
            setDraft(null)
            setResult({ ok: true, message: t('llm.result.cleared') })
        } catch (error) {
            setResult({ ok: false, message: formatLlmError(error, locale, t('llm.result.connectionFailed')) })
        }
    }

    const loading = configQuery.isFetching
    const saving = saveMutation.isPending
    const testing = testMutation.isPending
    const clearing = clearMutation.isPending
    const busy = loading || saving || testing || clearing
    const retryingFailedLoad = loading && configQuery.isFetched && configQuery.data === undefined
    const loadFailed = configQuery.isError || retryingFailedLoad

    return (
        <>
            <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6 flex flex-col gap-5">
                <p className="text-sm leading-6 text-muted-foreground">{t('llm.notice.desktop')}</p>
                {loadFailed ? (
                    <div className="flex flex-col gap-3 rounded-lg bg-red-500/10 px-3 py-3 text-sm text-red-500">
                        <span>{t('llm.result.loadFailed')}</span>
                        <button
                            type="button"
                            onClick={() => {
                                setResult(null)
                                void configQuery.refetch()
                            }}
                            disabled={busy}
                            data-testid="llm-config-retry"
                            className="self-start font-medium underline underline-offset-4 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            {t('llm.button.retry')}
                        </button>
                    </div>
                ) : null}
                <ConfigWarning message={partialConfigWarning} />
                <ConfigInput
                    id="llm-base-url"
                    label={t('llm.label.baseUrl')}
                    value={baseUrl}
                    onChange={(event) => edit('baseUrl', event.target.value)}
                    placeholder="https://api.openai.com/v1"
                    disabled={busy || loadFailed}
                />
                <ConfigInput
                    id="llm-api-key"
                    label={t('llm.label.apiKey')}
                    type="password"
                    value={apiKey}
                    onChange={(event) => edit('apiKey', event.target.value)}
                    placeholder={apiKeyConfigured ? t('llm.placeholder.savedApiKey') : 'sk-...'}
                    disabled={busy || loadFailed}
                    footer={apiKeyConfigured ? (
                        <p className="text-xs leading-5 text-muted-foreground" data-testid="llm-api-key-configured">
                            {t('llm.status.apiKeyConfigured')}
                        </p>
                    ) : null}
                />
                <ConfigInput
                    id="llm-model"
                    label={t('llm.label.model')}
                    value={model}
                    onChange={(event) => edit('model', event.target.value)}
                    placeholder="gpt-4o-mini"
                    disabled={busy || loadFailed}
                />
                <button
                    type="button"
                    onClick={save}
                    disabled={busy || loadFailed || !dirty || !completeDraft || Boolean(partialConfigWarning)}
                    data-testid="llm-config-save"
                    className="flex items-center justify-center h-10 rounded-[10px] border border-accent/25 bg-accent/8 text-accent hover:bg-accent/12 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
                >
                    {saving ? t('llm.button.saving') : t('llm.button.save')}
                </button>
                <button
                    type="button"
                    onClick={testConnection}
                    disabled={busy || loadFailed || dirty || !persistedConfig.configured}
                    data-testid="llm-config-test"
                    className="flex items-center justify-center h-10 rounded-[10px] border border-accent/25 text-accent hover:bg-accent/8 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
                >
                    {testing ? t('llm.button.testing') : t('llm.button.test')}
                </button>
                <button
                    type="button"
                    onClick={clear}
                    disabled={busy || (!loadFailed && !persistedConfig.configured)}
                    data-testid="llm-config-clear"
                    className="flex items-center justify-center h-10 rounded-[10px] border border-[var(--nw-glass-border)] text-sm font-medium text-muted-foreground transition-colors hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    {clearing ? t('llm.button.clearing') : t('llm.button.clearDesktop')}
                </button>
                <ConfigResult result={result} />
            </div>
            <ConfirmDialog {...dialogProps} />
        </>
    )
}

export function LlmConfigCard() {
    switch (getRuntimeMode()) {
        case 'hosted':
            return <HostedLlmConfigCard />
        case 'selfhost':
            return <SelfhostLlmConfigCard />
        case 'desktop':
            return <DesktopLlmConfigCard />
    }
}
