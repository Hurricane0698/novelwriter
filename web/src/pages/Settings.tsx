// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { AppearanceCard } from "@/components/settings/AppearanceCard"
import { LlmConfigCard } from "@/components/settings/LlmConfigCard"
import { useUiLocale } from "@/contexts/UiLocaleContext"

export default function Settings() {
    const { t } = useUiLocale()

    return (
        <div className="flex-1 flex flex-col items-center px-4 py-12">
            <div className="w-full max-w-[560px] flex flex-col gap-10">
                <h1 className="text-[28px] font-bold tracking-tight font-mono">
                    {t('settings.title')}
                </h1>

                <section className="flex flex-col gap-4">
                    <span className="text-xs font-semibold tracking-wider text-muted-foreground">
                        {t('settings.section.appearance')}
                    </span>
                    <AppearanceCard />
                </section>

                <section className="flex flex-col gap-4">
                    <span className="text-xs font-semibold tracking-wider text-muted-foreground">
                        {t('settings.section.ai')}
                    </span>
                    <LlmConfigCard />
                </section>

                <div className="pt-4 text-center text-sm text-muted-foreground">
                    <p>{t('settings.footer.version')}</p>
                </div>
            </div>
        </div>
    )
}
