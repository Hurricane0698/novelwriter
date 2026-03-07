import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

type SiteFooterProps = {
  compact?: boolean
  className?: string
}

const links = [
  { to: '/terms', label: '用户规则' },
  { to: '/privacy', label: '隐私说明' },
  { to: '/copyright', label: '版权投诉' },
]

export function SiteFooter({ compact, className }: SiteFooterProps) {
  return (
    <footer
      className={cn(
        'border-t border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.45)] backdrop-blur-xl',
        compact ? 'mt-8' : 'mt-20',
        className,
      )}
    >
      <div
        className={cn(
          'mx-auto flex w-full max-w-6xl flex-col gap-5 px-6',
          compact ? 'py-6 md:flex-row md:items-center md:justify-between' : 'py-8 md:flex-row md:items-center md:justify-between md:px-12',
        )}
      >
        <div className="flex flex-col gap-1">
          <div className="font-mono text-base font-bold text-foreground">NovWr</div>
          <p className="max-w-[34rem] text-sm leading-6 text-muted-foreground">
            面向长篇创作的 AI 辅助写作与续写工具。使用本服务前，请阅读相关规则、隐私说明与版权投诉说明。
          </p>
        </div>

        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="transition-colors hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  )
}
