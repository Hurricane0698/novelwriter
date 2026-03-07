// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
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

export default function Terms() {
  return (
    <LegalPageFrame
      eyebrow="NovWr · 用户规则"
      title="用户规则"
      summary="本规则用于说明你在使用 NovWr 软件及相关服务时应遵守的基本要求、内容边界与处理方式。请在使用相关功能前仔细阅读。"
      headerNote={`最后更新 ${LEGAL_LAST_UPDATED}`}
    >
      <Section title="1. 适用范围">
        <p>本规则适用于我们提供的 NovWr 官方网站、官方托管访问入口以及与 NovWr 软件发布相关的页面和服务。</p>
        <p>如你通过 Docker 或其他方式自行部署 NovWr，与你的部署环境、账号管理、数据存储、日志保留及对外运营相关的事项，由实际部署者自行负责。</p>
      </Section>

      <Section title="2. 服务性质">
        <p>NovWr 是一款基于人工智能的小说创作与续写辅助工具，提供文本续写、世界观整理与草稿生成能力。</p>
        <p>NovWr 生成的内容仅供创作参考，不构成法律、出版或知识产权意见，也不保证一定可直接公开发布。</p>
      </Section>

      <Section title="3. 你可以上传什么">
        <ul className="list-disc space-y-2 pl-5">
          <li>你原创的小说、设定、角色资料与提示词；</li>
          <li>你已经取得明确授权的作品内容；</li>
          <li>属于公共领域，或依法可以使用的内容。</li>
        </ul>
        <p>如你无法确认文本来源或授权状态，请勿上传或输入相关内容。</p>
      </Section>

      <Section title="4. 你不能这样使用">
        <ul className="list-disc space-y-2 pl-5">
          <li>上传、续写、改写或传播未经授权的受版权保护作品；</li>
          <li>利用 NovWr 生成违法违规、侵权、诽谤、骚扰或其他有害内容；</li>
          <li>绕过服务限制、批量刷接口、攻击系统或影响他人正常使用。</li>
        </ul>
      </Section>

      <Section title="5. AI 输出说明">
        <p>AI 生成内容可能存在事实错误、风格漂移、与现有作品相似、设定冲突或不符合预期的情况。</p>
        <p>你在对外发布、投稿、商业使用或传播前，应自行完成审查、修改与风险判断。NovWr 不会将 AI 草稿视为最终成稿。</p>
      </Section>

      <Section title="6. 我们如何处理风险内容">
        <p>如果我们发现，或收到第三方投诉认为相关内容存在侵权或违法违规风险，我们可以采取删除内容、隐藏结果、限制上传、暂停功能或终止服务等必要措施。</p>
        <p>对于重复侵权、明显高风险或恶意规避规则的使用行为，我们可直接限制继续使用。</p>
      </Section>

      <Section title="7. 相关页面">
        <p>
          使用本服务前，也建议一并阅读
          <Link to="/privacy" className="mx-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
            隐私说明
          </Link>
          与
          <Link to="/copyright" className="mx-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
            版权投诉说明
          </Link>
          。
        </p>
        <p>
          联系方式：
          {contactHref ? (
            <a href={contactHref} className="text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {LEGAL_CONTACT_LABEL}
            </a>
          ) : (
            <span className="text-foreground">{LEGAL_CONTACT_LABEL}</span>
          )}
        </p>
      </Section>
    </LegalPageFrame>
  )
}
