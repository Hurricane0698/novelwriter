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

export default function Privacy() {
  return (
    <LegalPageFrame
      eyebrow="NovWr · 隐私说明"
      title="隐私说明"
      summary="本说明用于介绍我们在提供 NovWr 软件及相关服务过程中如何处理相关信息，包括处理范围、处理目的、保存方式以及你可以行使的相关权利。"
      headerNote={`最后更新 ${LEGAL_LAST_UPDATED}`}
    >
      <Section title="1. 适用范围">
        <p>本说明适用于我们提供的 NovWr 官方网站、官方托管访问入口及相关服务。</p>
        <p>如你使用的是第三方或自行部署的 NovWr 实例，相关信息处理规则应以实际部署者另行提供的说明为准。</p>
      </Section>

      <Section title="2. 我们会处理哪些信息">
        <ul className="list-disc space-y-2 pl-5">
          <li>账号相关信息，如昵称、登录状态、基础配额信息；</li>
          <li>你主动上传或输入的内容，如章节正文、世界观设定、角色关系、续写指令；</li>
          <li>NovWr 生成的结果，以及为保证服务可用而记录的基础日志与错误信息。</li>
        </ul>
      </Section>

      <Section title="3. 我们为什么处理这些信息">
        <p>这些信息主要用于提供续写、保存作品、展示历史结果、处理故障、做基本风控，以及改进产品体验。</p>
        <p>除法律法规另有要求或经你另行授权外，我们不会超出实现服务所必需的范围使用相关信息。</p>
      </Section>

      <Section title="4. 第三方模型服务">
        <p>当你发起生成请求时，相关章节上下文、世界设定和续写指令可能会被发送给当前接入的模型服务提供方，以完成生成任务。</p>
        <p>我们会尽量把传递范围控制在生成所必需的上下文内，但模型处理本身属于服务链路的一部分。</p>
      </Section>

      <Section title="5. 保存与删除">
        <p>你上传的作品和生成结果通常会保留到你主动删除为止。你已经可以在作品库中删除作品，我们会同步清理相关文件与记录。</p>
        <p>基础日志与安全记录仅在满足排障、安全防护和风险治理所需的合理期限内保留。</p>
      </Section>

      <Section title="6. 你的选择权">
        <p>你可以决定是否上传作品、是否继续使用生成服务，以及是否删除已创建的作品。</p>
        <p>
          如果你需要进一步删除账号、导出数据或反馈隐私问题，可通过以下方式联系我们：
          {contactHref ? (
            <a href={contactHref} className="ml-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {LEGAL_CONTACT_LABEL}
            </a>
          ) : (
            <span className="ml-1 text-foreground">{LEGAL_CONTACT_LABEL}</span>
          )}
        </p>
      </Section>
    </LegalPageFrame>
  )
}
