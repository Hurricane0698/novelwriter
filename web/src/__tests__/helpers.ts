import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Keep cached data around during a test run.
        // `gcTime: 0` can evict `setQueryData` results immediately for keys with no active observers,
        // which makes cache-assertion tests flaky across runtimes/CI.
        gcTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export function createQueryClientWrapper(queryClient = createTestQueryClient()) {
  return function QueryClientTestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}
