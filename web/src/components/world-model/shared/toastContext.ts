import { createContext } from 'react'

export interface ToastContextType {
  toast: (message: string) => void
}

export const ToastContext = createContext<ToastContextType | null>(null)
