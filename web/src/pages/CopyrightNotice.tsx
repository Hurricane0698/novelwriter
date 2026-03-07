// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
import { GlassCard } from '@/components/GlassCard'
import { LegalPageFrame } from '@/components/legal/LegalPageFrame'
import { LEGAL_LAST_UPDATED, LEGAL_CONTACT_LABEL, getLegalContactHref } from '@/content/legal'

const contactHref = getLegalContactHref()

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <GlassCard className="px-6 py-6 md:px-8 md:py-7">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-mono text-xl font-semibold text-foreground md:text-2xl">{title}</h2>
          <span className="text-xs text-muted-foreground">{LEGAL_LAST_UPDATED}</span>
        </div>
        <div className="space-y-3 text-sm leading-7 text-muted-foreground md:text-[15px]">{children}</div>
      </div>
    </GlassCard>
  )
}

export default function CopyrightNotice() {
  return (
    <LegalPageFrame
      eyebrow="NovWr · 版权投诉"
      title="版权投诉说明"
      summary="如你认为通过 NovWr 官方托管入口提供或展示的相关内容侵犯了你的合法权益，可按本说明提交通知。我们将在收到完整材料后按流程进行核查与处理。"
      headerNote={`最后更新 ${LEGAL_LAST_UPDATED}`}
    >
      <Section title="1. 适用范围">
        <p>本说明适用于通过 NovWr 官方托管访问入口提供或展示的相关内容。</p>
        <p>如相关内容来自第三方或用户自行部署的 NovWr 实例，请优先联系对应实例的实际部署者或运营者处理。</p>
      </Section>

      <Section title="2. 如何提交投诉">
        <p>如果你认为通过 NovWr 官方托管入口提供或展示的某些内容侵犯了你的合法权益，请尽量一次性提供完整信息，以便我们快速核查。</p>
        <ul className="list-disc space-y-2 pl-5">
          <li>你的姓名或名称、联系方式；</li>
          <li>能够证明你享有相关权利的材料或说明；</li>
          <li>被投诉内容的标题、截图、链接或其他可定位信息；</li>
          <li>你认为构成侵权的理由说明。</li>
        </ul>
      </Section>

      <Section title="3. 我们会怎么做">
        <p>收到投诉后，我们会先做基础核查，并可能根据风险程度先行隐藏、删除、限制访问或暂停相关功能，以防问题继续扩大。</p>
        <p>如果用户多次上传高风险内容，我们可进一步限制其继续使用。</p>
      </Section>

      <Section title="4. 如果你是被投诉用户">
        <p>如果你认为投诉存在误解，也可以主动联系我们说明情况，并补充你的授权、来源或创作证明材料。</p>
        <p>在核查期间，我们可能根据具体情况暂时隐藏、删除或限制相关内容的访问与使用。</p>
      </Section>

      <Section title="5. 联系方式">
        <p>
          投诉邮箱：
          {contactHref ? (
            <a href={contactHref} className="text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {LEGAL_CONTACT_LABEL}
            </a>
          ) : (
            <span className="text-foreground">{LEGAL_CONTACT_LABEL}</span>
          )}
        </p>
        {!contactHref ? (
          <p className="rounded-xl border border-dashed border-[var(--nw-glass-border-hover)] bg-white/5 px-4 py-3 text-foreground/80">
            当前未配置公开联系邮箱。正式对外发布前，请在环境变量中设置 `VITE_LEGAL_CONTACT_EMAIL`。
          </p>
        ) : null}
      </Section>
    </LegalPageFrame>
  )
}
