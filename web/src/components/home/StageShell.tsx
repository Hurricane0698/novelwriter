// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type StageShellProps = {
  label?: ReactNode
  accentHex?: string
  className?: string
  headerClassName?: string
  bodyClassName?: string
  children: ReactNode
}

export function StageShell({
  label = 'NovWr',
  accentHex = '#5b6bf0',
  className,
  headerClassName,
  bodyClassName,
  children,
}: StageShellProps) {
  const resolvedLabel = typeof label === 'string'
    ? (
        <span className="ml-auto font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400">
          {label}
        </span>
      )
    : label

  return (
    <div
      className={cn(
        'relative flex w-full flex-col overflow-hidden rounded-[28px] border border-black/8 bg-white shadow-[0_32px_72px_rgba(15,23,42,0.10)]',
        className,
      )}
    >
      <div
        className={cn('flex h-10 shrink-0 items-center border-b bg-white/92 px-4 backdrop-blur-sm', headerClassName)}
        style={{ borderBottomColor: `${accentHex}22` }}
      >
        <div className="flex gap-1.5">
          <div className="h-2.5 w-2.5 rounded-full bg-slate-300" />
          <div className="h-2.5 w-2.5 rounded-full bg-slate-300" />
          <div className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        </div>
        {resolvedLabel}
      </div>
      <div className={cn('relative bg-white', bodyClassName)}>{children}</div>
    </div>
  )
}
