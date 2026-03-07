import type { ReactNode } from 'react'
import { ToastProvider } from '@/components/world-model/shared/Toast'

/**
 * WorldModel module shell.
 *
 * WorldModel hooks/components are allowed to use module-scoped providers
 * (e.g. toast). Any future embedding should wrap with this shell.
 */
export function WorldModelShell({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>
}
