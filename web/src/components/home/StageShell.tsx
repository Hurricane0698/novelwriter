// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type StageShellProps = {
  label?: ReactNode
  headerAction?: ReactNode
  className?: string
  headerClassName?: string
  bodyClassName?: string
  children: ReactNode
}

export function StageShell({
  label = 'NovWr',
  headerAction,
  className,
  headerClassName,
  bodyClassName,
  children,
}: StageShellProps) {
  const resolvedLabel = typeof label === 'string'
    ? (
        <span className="ml-4 text-xs text-[hsl(var(--lp-ink)/0.6)]">
          {label}
        </span>
      )
    : label

  return (
    <div
      className={cn(
        'relative flex w-full flex-col overflow-hidden rounded-[20px] border border-[hsl(var(--lp-ink)/0.08)] bg-[hsl(var(--lp-frame))] shadow-none',
        className,
      )}
    >
      <div
        className={cn(
          'flex h-10 shrink-0 items-center border-b border-[hsl(var(--lp-ink)/0.08)] bg-[hsl(var(--lp-paper))] px-4',
          headerClassName,
        )}
      >
        <div className="flex gap-1.5">
          <div className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--lp-ink)/0.12)]" />
          <div className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--lp-ink)/0.12)]" />
          <div className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--lp-ink)/0.12)]" />
        </div>
        {resolvedLabel}
        {headerAction ? <div className="ml-auto pl-3">{headerAction}</div> : null}
      </div>
      <div className={cn('relative bg-[hsl(var(--lp-frame))]', bodyClassName)}>{children}</div>
    </div>
  )
}
