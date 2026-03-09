import { useState, useEffect } from "react"
import { getLlmApiErrorMessage, getLlmConfigWarning } from "@/lib/llmErrorMessages"
import { api, ApiError } from "@/services/api"
import { clearLlmConfig, getLlmConfig, setLlmConfig } from "@/lib/llmConfigStore"

const IS_HOSTED = (import.meta.env.VITE_DEPLOY_MODE || "selfhost") === "hosted"

export function LlmConfigCard() {
    const [baseUrl, setBaseUrl] = useState("")
    const [apiKey, setApiKey] = useState("")
    const [model, setModel] = useState("")
    const [testing, setTesting] = useState(false)
    const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

    useEffect(() => {
        const config = getLlmConfig()
        setBaseUrl(config.baseUrl)
        setApiKey(config.apiKey)
        setModel(config.model)
    }, [])

    const save = () => {
        setLlmConfig({
            baseUrl: baseUrl.trim(),
            apiKey: apiKey.trim(),
            model: model.trim(),
        })
    }
    const partialConfigWarning = getLlmConfigWarning({
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
        model: model.trim(),
    })

    const testConnection = async () => {
        save()
        setTesting(true)
        setResult(null)
        try {
            const res = await api.testLlmConnection()
            if (res.ok) {
                setResult({ ok: true, message: res.message ?? `连接与应用兼容性检测通过 (${res.latency_ms}ms)` })
            } else {
                setResult({ ok: false, message: res.error ?? "连接失败" })
            }
        } catch (e) {
            if (e instanceof ApiError) {
                setResult({ ok: false, message: getLlmApiErrorMessage(e) ?? `请求失败（HTTP ${e.status}）` })
            } else {
                setResult({ ok: false, message: e instanceof Error ? e.message : "连接失败" })
            }
        } finally {
            setTesting(false)
        }
    }

    return (
        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6 flex flex-col gap-5">
            {IS_HOSTED ? (
                <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-white/5 px-4 py-3.5 text-sm leading-6 text-muted-foreground">
                    在线版也支持填写你自己的 API Key，但请先知晓风险：密钥会在模型请求时通过当前实例服务器转发到你配置的 OpenAI 兼容接口。
                    当前实现不会把这类用户自带密钥持久化到浏览器或服务端；它只保留在当前标签页内存里，刷新页面后会清空。
                    如果你对当前部署实例的运维环境不完全信任，建议不要在在线版填写，改用 Docker 自部署。
                </div>
            ) : (
                <p className="text-sm leading-6 text-muted-foreground">
                    出于安全考虑，这里的配置只保留在当前浏览器标签页内存中；刷新页面后会清空。
                    如果你想长期使用自己的 Key，推荐改用 Docker / 环境变量自部署。
                </p>
            )}

            {partialConfigWarning ? (
                <div className="rounded-lg border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.10)] px-3 py-2 text-sm text-[hsl(var(--color-warning))]">
                    {partialConfigWarning}
                </div>
            ) : null}

            <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium" htmlFor="llm-base-url">
                    API Base URL
                </label>
                <input
                    id="llm-base-url"
                    type="text"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    onBlur={save}
                    placeholder="https://api.openai.com/v1"
                    className="h-10 rounded-lg border border-[var(--nw-glass-border)] bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                />
            </div>

            <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium" htmlFor="llm-api-key">
                    API Key
                </label>
                <input
                    id="llm-api-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    onBlur={save}
                    placeholder="sk-..."
                    className="h-10 rounded-lg border border-[var(--nw-glass-border)] bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                />
            </div>

            <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium" htmlFor="llm-model">
                    Model Name
                </label>
                <input
                    id="llm-model"
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    onBlur={save}
                    placeholder="gpt-4o-mini"
                    className="h-10 rounded-lg border border-[var(--nw-glass-border)] bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                />
            </div>

            <button
                type="button"
                onClick={testConnection}
                disabled={testing || !baseUrl || !apiKey || !model}
                className="flex items-center justify-center h-10 rounded-[10px] border border-accent/25 text-accent hover:bg-accent/8 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
            >
                {testing ? "测试中..." : "测试连接"}
            </button>

            <button
                type="button"
                onClick={() => {
                    clearLlmConfig()
                    setBaseUrl("")
                    setApiKey("")
                    setModel("")
                    setResult(null)
                }}
                className="flex items-center justify-center h-10 rounded-[10px] border border-[var(--nw-glass-border)] text-sm font-medium text-muted-foreground transition-colors hover:bg-white/5"
            >
                清空当前标签页配置
            </button>

            {result && (
                <div
                    className={`text-sm px-3 py-2 rounded-lg ${
                        result.ok
                            ? "bg-green-500/10 text-green-500"
                            : "bg-red-500/10 text-red-500"
                    }`}
                >
                    {result.message}
                </div>
            )}
        </div>
    )
}
