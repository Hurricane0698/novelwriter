// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { motion } from 'framer-motion'

type NarrativeVariant = 'editorial' | 'thread'

type NarrativeActProps = {
    eyebrow: string
    title: string
    description: string
    bullets: string[]
    isActive: boolean
    accentHex: string
    prefersReducedMotion: boolean
    stepLabel: string
    variant?: NarrativeVariant
}

export function NarrativeAct({
    eyebrow,
    title,
    description,
    bullets,
    isActive,
    accentHex,
    prefersReducedMotion,
    stepLabel,
    variant = 'editorial',
}: NarrativeActProps) {
    return (
        <motion.div
            className="flex min-h-[94vh] items-center py-16 lg:min-h-[102vh]"
            animate={{ opacity: isActive ? 1 : 0.45, y: isActive ? 0 : 8 }}
            transition={{ duration: prefersReducedMotion ? 0 : 0.45 }}
        >
            {variant === 'thread' ? (
                <ThreadAct
                    stepLabel={stepLabel}
                    eyebrow={eyebrow}
                    title={title}
                    description={description}
                    bullets={bullets}
                    accentHex={accentHex}
                />
            ) : (
                <EditorialAct
                    stepLabel={stepLabel}
                    eyebrow={eyebrow}
                    title={title}
                    description={description}
                    bullets={bullets}
                    accentHex={accentHex}
                />
            )}
        </motion.div>
    )
}

/* ── Editorial ──────────────────────────────────────────────────────
   Oversized watermark step number, accent dash line, dash bullets.
   Clean, confident, magazine-inspired. No cards.
   ─────────────────────────────────────────────────────────────────── */
function EditorialAct({
    stepLabel,
    eyebrow,
    title,
    description,
    bullets,
    accentHex,
}: Omit<NarrativeActProps, 'isActive' | 'prefersReducedMotion' | 'variant'>) {
    return (
        <div className="relative max-w-[500px]">
            {/* Oversized watermark number */}
            <div
                className="pointer-events-none absolute -left-3 -top-12 select-none font-sans tracking-tighter text-[150px] font-black leading-none"
                style={{ color: accentHex, opacity: 0.04 }}
            >
                {stepLabel}
            </div>

            <div className="relative flex items-center gap-4">
                <span
                    className="font-mono text-[11px] font-bold tracking-[0.18em]"
                    style={{ color: accentHex }}
                >
                    {stepLabel}
                </span>
                <div
                    className="h-[2px] w-10 rounded-full"
                    style={{ backgroundColor: accentHex }}
                />
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/60">
                    {eyebrow}
                </span>
            </div>

            <h3 className="mt-7 font-sans tracking-tight text-[32px] font-bold leading-[1.10] text-foreground lg:text-[38px]">
                {title}
            </h3>

            <p className="mt-5 max-w-[450px] text-[15px] leading-8 text-muted-foreground lg:text-base">
                {description}
            </p>

            <div className="mt-8 space-y-4">
                {bullets.map((bullet, i) => (
                    <div key={i} className="flex items-start gap-3.5">
                        <span
                            className="mt-3 h-[2px] w-5 shrink-0 rounded-full"
                            style={{ backgroundColor: `${accentHex}60` }}
                        />
                        <span className="text-sm leading-7 text-muted-foreground">
                            {bullet}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    )
}

/* ── Thread ──────────────────────────────────────────────────────────
   Vertical accent stem on left with dot anchor, indented content.
   Organic flow, timeline-like without being a literal timeline.
   ─────────────────────────────────────────────────────────────────── */
function ThreadAct({
    stepLabel,
    eyebrow,
    title,
    description,
    bullets,
    accentHex,
}: Omit<NarrativeActProps, 'isActive' | 'prefersReducedMotion' | 'variant'>) {
    return (
        <div className="relative max-w-[500px] pl-9">
            {/* Vertical accent thread */}
            <div
                className="absolute bottom-2 left-0 top-1 w-[2px] rounded-full"
                style={{
                    background: `linear-gradient(180deg, ${accentHex} 0%, ${accentHex}12 100%)`,
                }}
            />

            {/* Dot anchor at top of thread */}
            <div
                className="absolute -left-[5px] top-0 h-3 w-3 rounded-full"
                style={{ backgroundColor: accentHex }}
            />

            <div className="flex items-baseline gap-3">
                <span
                    className="font-sans tracking-tight text-[28px] font-black leading-none"
                    style={{ color: accentHex }}
                >
                    {stepLabel}
                </span>
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/60">
                    {eyebrow}
                </span>
            </div>

            <h3 className="mt-6 font-sans tracking-tight text-[30px] font-bold leading-[1.12] text-foreground lg:text-[35px]">
                {title}
            </h3>

            <p className="mt-5 text-[15px] leading-8 text-muted-foreground lg:text-base">
                {description}
            </p>

            <div className="mt-7 space-y-3.5">
                {bullets.map((bullet, i) => (
                    <div key={i} className="flex items-start gap-3">
                        <span
                            className="mt-0.5 font-mono text-[12px] font-bold leading-7"
                            style={{ color: accentHex }}
                        >
                            {String(i + 1).padStart(2, '0')}
                        </span>
                        <span className="text-sm leading-7 text-muted-foreground">
                            {bullet}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    )
}
