// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: MIT

import { GlassSurface } from '@/components/ui/glass-surface'
import { NwButton } from '@/components/ui/nw-button'
import type { StudioPreparationGateState } from '@/hooks/novel/studioOnboardingPreparation'

export function StudioPreparationGate({
  title,
  description,
  detail,
  error,
  primaryActionLabel,
  onRetry, onReturn, retryable,
  primaryActionPending,
  secondaryActionLabel,
}: StudioPreparationGateState & { primaryActionPending: boolean; onRetry: () => void; onReturn: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center px-8 py-10" data-testid="studio-preparation-gate">
      <GlassSurface
        variant="container"
        className="w-full max-w-2xl rounded-[28px] border border-[var(--nw-glass-border)] px-8 py-9 shadow-[var(--nw-copilot-panel-shadow)]"
      >
        <div className="flex flex-col items-center gap-5 text-center">
          {!error ? (
            <div className="h-11 w-11 animate-spin rounded-full border-2 border-[hsl(var(--accent)/0.18)] border-t-[hsl(var(--accent))]" />
          ) : null}
          <div className="space-y-2">
            <h2 className="m-0 text-2xl font-semibold tracking-tight text-foreground">{title}</h2>
            <p className="m-0 text-sm leading-6 text-muted-foreground">{description}</p>
          </div>
          {detail ? (
            <div className="rounded-full border border-[var(--nw-glass-border)] bg-[hsl(var(--foreground)/0.04)] px-4 py-2 text-sm text-foreground/90">
              {detail}
            </div>
          ) : null}
          {error ? (
            <div
              role="alert"
              data-testid="studio-preparation-error"
              className="w-full rounded-2xl border border-[hsl(var(--color-warning)/0.3)] bg-[hsl(var(--color-warning)/0.08)] px-4 py-3 text-sm text-[hsl(var(--color-warning))] whitespace-pre-wrap"
            >
              {error}
            </div>
          ) : null}
          {primaryActionLabel || secondaryActionLabel ? (
            <div className="flex flex-wrap items-center justify-center gap-3">
              {primaryActionLabel ? (
                <NwButton
                  variant="accent"
                  className="rounded-full px-5 py-2.5 text-sm font-semibold"
                  onClick={retryable ? onRetry : onReturn}
                  disabled={primaryActionPending}
                  data-testid="studio-preparation-primary-action"
                >
                  {primaryActionLabel}
                </NwButton>
              ) : null}
              {secondaryActionLabel ? (
                <NwButton
                  variant="glass"
                  className="rounded-full px-5 py-2.5 text-sm font-semibold"
                  onClick={onReturn}
                  disabled={primaryActionPending}
                  data-testid="studio-preparation-secondary-action"
                >
                  {secondaryActionLabel}
                </NwButton>
              ) : null}
            </div>
          ) : null}
        </div>
      </GlassSurface>
    </div>
  )
}
