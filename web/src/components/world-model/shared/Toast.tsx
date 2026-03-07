import { useCallback, useState } from 'react'
import { cn } from '@/lib/utils'
import { GlassSurface } from '@/components/ui/glass-surface'
import { ToastContext } from './toastContext'

interface Toast {
  id: number
  message: string
}

let nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((message: string) => {
    const id = nextId++
    setToasts(prev => [...prev, { id, message }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000)
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2">
        {toasts.map(t => (
          <GlassSurface
            key={t.id}
            variant="floating"
            className={cn(
              'w-[min(560px,calc(100vw-2rem))]',
              'rounded-xl px-4 py-2 text-sm',
              'shadow-[0_10px_30px_rgba(0,0,0,0.55)]', // override default for toast weight
              'border-l-4 border-l-[hsl(var(--color-warning))]',
              'animate-in fade-in slide-in-from-bottom-2'
            )}
          >
            {t.message}
          </GlassSurface>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
