import type { ReactNode } from 'react'
import { GlassCard } from '@/components/GlassCard'
import { SiteFooter } from '@/components/layout/SiteFooter'

type LegalPageFrameProps = {
  eyebrow: string
  title: string
  summary: string
  headerNote?: string
  children: ReactNode
}

export function LegalPageFrame({ eyebrow, title, summary, headerNote, children }: LegalPageFrameProps) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10 md:px-10 md:py-14">
        <GlassCard className="relative overflow-hidden border-[var(--nw-glass-border-hover)] px-6 py-8 md:px-10 md:py-10">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.28em] text-accent/90">
              <span>{eyebrow}</span>
              {headerNote ? (
                <span className="text-[11px] font-medium tracking-[0.2em] text-muted-foreground">
                  {headerNote}
                </span>
              ) : null}
            </div>
            <div className="flex flex-col gap-3">
              <h1 className="max-w-3xl font-mono text-4xl font-bold leading-tight text-foreground md:text-5xl">
                {title}
              </h1>
              <p className="max-w-3xl text-base leading-7 text-muted-foreground md:text-lg md:leading-8">
                {summary}
              </p>
            </div>
          </div>
        </GlassCard>

        <div className="flex flex-col gap-4">{children}</div>
      </div>

      <SiteFooter compact className="mt-auto" />
    </div>
  )
}
