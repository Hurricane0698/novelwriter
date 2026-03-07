// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { AppearanceCard } from "@/components/settings/AppearanceCard"
import { AccountCard } from "@/components/settings/AccountCard"
import { LlmConfigCard } from "@/components/settings/LlmConfigCard"
import { useAuth } from "@/contexts/AuthContext"

export default function Settings() {
    const { isLoggedIn } = useAuth()

    return (
        <div className="flex-1 flex flex-col items-center px-4 py-12">
            <div className="w-full max-w-[560px] flex flex-col gap-10">
                <h1 className="text-[28px] font-bold tracking-tight font-mono">
                    设置
                </h1>

                {/* Appearance Section */}
                <section className="flex flex-col gap-4">
                    <span className="text-xs font-semibold tracking-wider text-muted-foreground">
                        外观
                    </span>
                    <AppearanceCard />
                </section>

                {/* LLM Config Section */}
                <section className="flex flex-col gap-4">
                    <span className="text-xs font-semibold tracking-wider text-muted-foreground">
                        AI 模型配置
                    </span>
                    <LlmConfigCard />
                </section>

                {/* Account Section — only when logged in */}
                {isLoggedIn && (
                    <section className="flex flex-col gap-4">
                        <span className="text-xs font-semibold tracking-wider text-muted-foreground">
                            账户
                        </span>
                        <AccountCard />
                    </section>
                )}

                {/* Footer */}
                <div className="pt-4 text-center text-sm text-muted-foreground">
                    <p>NovWr v0.01 Beta</p>
                </div>
            </div>
        </div>
    )
}
