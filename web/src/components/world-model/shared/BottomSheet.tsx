import { useEffect } from 'react'
import { cn } from '@/lib/utils'
import { GlassSurface } from '@/components/ui/glass-surface'

export function BottomSheet({ open, onClose, children }: {
  open: boolean
  onClose: () => void
  children: React.ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  return (
    <>
      <div
        className={cn(
          'fixed inset-0 z-40 bg-[var(--nw-backdrop)] transition-opacity',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          'fixed inset-x-0 bottom-0 z-50 transition-transform duration-200',
          open ? 'translate-y-0' : 'translate-y-full'
        )}
        data-testid="bottom-sheet"
        data-open={open ? 'true' : 'false'}
      >
        <div className="mx-auto w-full max-w-3xl">
          <GlassSurface
            variant="floating"
            className="rounded-t-2xl shadow-[0_-30px_80px_rgba(0,0,0,0.65)]"
          >
            <div className="flex justify-center pt-2">
              <div className="h-1 w-10 rounded-full bg-[hsl(var(--foreground)/0.16)]" />
            </div>
            <div className="p-4 max-h-[75vh] overflow-y-auto">
              {children}
            </div>
          </GlassSurface>
        </div>
      </div>
    </>
  )
}
