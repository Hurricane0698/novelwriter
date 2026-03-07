// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/contexts/AuthContext"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useConfirmDialog } from "@/hooks/useConfirmDialog"
import { AnimatedBackground } from "@/components/layout/AnimatedBackground"
import { NwButton } from "@/components/ui/nw-button"
import { ApiError } from "@/services/api"

const DEPLOY_MODE = import.meta.env.VITE_DEPLOY_MODE || "selfhost"

function getPostLoginDestination(state: unknown): string {
    if (!state || typeof state !== "object" || !("from" in state)) return "/library"

    const from = state.from
    if (typeof from !== "string") return "/library"
    if (!from.startsWith("/") || from.startsWith("//")) return "/library"
    if (from === "/login" || from.startsWith("/login?")) return "/library"

    return from
}

export default function Login() {
    const isHosted = DEPLOY_MODE === "hosted"

    // Hosted mode fields
    const [inviteCode, setInviteCode] = useState("")
    const [nickname, setNickname] = useState("")

    // Selfhost mode fields
    const [username, setUsername] = useState("")
    const [password, setPassword] = useState("")

    const [isLoading, setIsLoading] = useState(false)
    const { login, inviteRegister } = useAuth()
    const location = useLocation()
    const navigate = useNavigate()
    const { alert, dialogProps } = useConfirmDialog()
    const postLoginDestination = getPostLoginDestination(location.state)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        setIsLoading(true)
        try {
            if (isHosted) {
                if (!inviteCode || !nickname) return
                await inviteRegister(inviteCode, nickname)
            } else {
                if (!username || !password) return
                await login(username, password)
            }
            navigate(postLoginDestination, { replace: true })
        } catch (err) {
            if (err instanceof ApiError) {
                const requestIdSuffix = err.requestId ? `（Request ID: ${err.requestId}）` : ""

                if (isHosted && err.status === 403) {
                    await alert({ title: "邀请码无效", description: `请检查邀请码是否正确${requestIdSuffix}` })
                } else if (err.status === 401) {
                    await alert({ title: "登录失败", description: `用户名或密码错误${requestIdSuffix}` })
                } else if (err.status === 404) {
                    await alert({
                        title: "连接失败",
                        description:
                            "无法连接到后端（/api 404）。如果你在 WSL + Windows 浏览器开发，请确认后端已启动，并重启前端 dev server 以生效 Vite /api 代理。" +
                            requestIdSuffix,
                    })
                } else {
                    await alert({ title: "操作失败", description: `请求失败（HTTP ${err.status}）。请稍后重试${requestIdSuffix}` })
                }
                return
            }

            await alert({
                title: "连接失败",
                description: "无法连接到后端，请确认后端已启动（以及前端是否通过 /api 代理）。",
            })
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="min-h-screen grid items-center justify-center relative overflow-hidden">
            <AnimatedBackground />

            <div className="w-[420px] z-10 rounded-[20px] p-10 bg-[var(--nw-glass-bg)] backdrop-blur-[24px] border border-[var(--nw-glass-border)] flex flex-col gap-8">
                {/* Header */}
                <div className="flex flex-col gap-3 w-full">
                    <span className="font-mono text-[28px] font-bold text-foreground">NovWr</span>
                    <span className="font-sans text-[15px] text-muted-foreground">
                        {isHosted ? "输入邀请码开始体验" : "登录到你的账户"}
                    </span>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="flex flex-col gap-5 w-full" data-testid="login-form">
                    {isHosted ? (
                        <>
                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="invite-code">
                                    邀请码
                                </label>
                                <Input
                                    id="invite-code"
                                    type="text"
                                    value={inviteCode}
                                    onChange={(e) => setInviteCode(e.target.value)}
                                    placeholder="从 Linux.do 帖子获取"
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    required
                                />
                            </div>
                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="nickname">
                                    昵称
                                </label>
                                <Input
                                    id="nickname"
                                    type="text"
                                    value={nickname}
                                    onChange={(e) => setNickname(e.target.value)}
                                    placeholder="你的显示名称"
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    required
                                />
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="username">
                                    用户名
                                </label>
                                <Input
                                    id="username"
                                    type="text"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    required
                                />
                            </div>
                            <div className="flex flex-col gap-1.5 w-full">
                                <label className="text-sm font-medium leading-none" htmlFor="password">
                                    密码
                                </label>
                                <Input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="border-[var(--nw-glass-border)] bg-transparent rounded-lg h-10 focus-visible:ring-2 focus-visible:ring-accent"
                                    required
                                />
                            </div>
                        </>
                    )}

                    <NwButton
                        type="submit"
                        disabled={isLoading}
                        data-testid="login-submit"
                        variant="accent"
                        className="w-full h-11 rounded-xl font-medium text-sm shadow-[0_0_20px_hsl(var(--accent)/0.40)] transition-[background-color,box-shadow] hover:shadow-[0_0_28px_hsl(var(--accent)/0.55)]"
                    >
                        {isLoading ? "请稍候..." : isHosted ? "开始体验" : "登录"}
                    </NwButton>

                    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-1 text-xs text-muted-foreground">
                        <Link to="/terms" className="transition-colors hover:text-foreground">用户规则</Link>
                        <Link to="/privacy" className="transition-colors hover:text-foreground">隐私说明</Link>
                        <Link to="/copyright" className="transition-colors hover:text-foreground">版权投诉</Link>
                    </div>
                </form>
            </div>
            <ConfirmDialog {...dialogProps} />
        </div>
    )
}
