// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PerformanceModeProvider } from '@/contexts/PerformanceModeContext'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { PageShell } from '@/components/layout/PageShell'
import { getRuntimeMode } from '@/lib/runtimeMode'
import { DesktopExitGuard } from '@/components/DesktopExitGuard'
import { CandidateDraftPersistence } from '@/components/CandidateDraftPersistence'

const Home = lazy(() => import('@/pages/Home'))
const Settings = lazy(() => import('@/pages/Settings'))
const LibraryPage = lazy(() => import('@/pages/LibraryPage').then((module) => ({ default: module.LibraryPage })))
const NovelStudioPage = lazy(() => import('@/pages/NovelStudioPage').then((module) => ({ default: module.NovelStudioPage })))
const NovelAtlasPage = lazy(() => import('@/pages/NovelAtlasPage').then((module) => ({ default: module.NovelAtlasPage })))
const NovelShell = lazy(() => import('@/components/novel-shell/NovelShell').then((module) => ({ default: module.NovelShell })))

const queryClient = new QueryClient()

function RouteLoading() {
  return <div role="status" className="p-8">{document.documentElement.lang.startsWith('en')
    ? 'Loading NovWr…' : '正在加载 NovWr…'}</div>
}

function Layout() {
  const { pathname } = useLocation()
  const isWorld = pathname.startsWith('/world/')
  return (
    <PageShell
      // Atlas manages its own full-height layout + scroll containers.
      // Make the shell fixed-height to avoid the whole page scrolling when sidebars overflow.
      showNavbar={!isWorld}
      className={isWorld ? 'h-screen overflow-hidden' : undefined}
      mainClassName={isWorld ? 'min-h-0 overflow-hidden' : undefined}
    >
      <Outlet />
    </PageShell>
  )
}

function HomeRoute() {
  if (getRuntimeMode() === 'desktop') {
    return <Navigate to="/library" replace />
  }
  return <Home />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <CandidateDraftPersistence />
      <UiLocaleProvider>
        <DesktopExitGuard />
        <BrowserRouter>
          <PerformanceModeProvider>
            <Suspense fallback={<RouteLoading />}>
              <Routes>
                <Route element={<Layout />}>
                  <Route path="/" element={<HomeRoute />} />
                  <Route path="/settings" element={<Settings />} />
                </Route>
                <Route path="/library" element={<LibraryPage />} />
                <Route element={<NovelShell />}>
                  <Route element={<Layout />}>
                    <Route path="/world/:novelId" element={<NovelAtlasPage />} />
                  </Route>
                  <Route path="/novel/:novelId" element={<NovelStudioPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </PerformanceModeProvider>
        </BrowserRouter>
      </UiLocaleProvider>
    </QueryClientProvider>
  )
}
