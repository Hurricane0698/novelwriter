import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { NovelCopilotProvider } from '@/components/novel-copilot/NovelCopilotProvider'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import { createTestQueryClient } from './queryClient'

export function createNovelWrapper(client = createTestQueryClient(), novelId = 7) {
  return function NovelTestProviders({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>
      <UiLocaleProvider>
        <ToastProvider>
          <NovelCopilotProvider novelId={novelId}>{children}</NovelCopilotProvider>
        </ToastProvider>
      </UiLocaleProvider>
    </QueryClientProvider>
  }
}
