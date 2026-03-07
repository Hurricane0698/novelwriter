// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { PageShell } from '@/components/layout/PageShell'
import { Home } from '@/pages/Home'
import { LibraryPage } from '@/pages/LibraryPage'
import { NovelDetailPage } from '@/pages/NovelDetailPage'
import { WritingWorkspace } from '@/pages/WritingWorkspace'
import { GenerationResults } from '@/pages/GenerationResults'
import { WorldModel } from '@/pages/WorldModel'

const Login = lazy(() => import('@/pages/Login'))
const Settings = lazy(() => import('@/pages/Settings'))
const Terms = lazy(() => import('@/pages/Terms'))
const Privacy = lazy(() => import('@/pages/Privacy'))
const CopyrightNotice = lazy(() => import('@/pages/CopyrightNotice'))

const queryClient = new QueryClient()

/** Shared shell (animated background + navbar). */
function Layout() {
  const { pathname } = useLocation()
  const isWorld = pathname.startsWith('/world/')
  return (
    <PageShell
      // WorldModel manages its own full-height layout + scroll containers.
      // Make the shell fixed-height to avoid the whole page scrolling when sidebars overflow.
      showNavbar={!isWorld}
      className={isWorld ? 'h-screen overflow-hidden' : undefined}
      mainClassName={isWorld ? 'min-h-0 overflow-hidden' : undefined}
    >
      <Outlet />
    </PageShell>
  )
}

function RequireAuth() {
  const { isLoggedIn, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return null
  if (!isLoggedIn) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Suspense fallback={null}>
            <Routes>
              {/* Old-layout pages */}
              <Route element={<Layout />}>
                <Route path="/" element={<Home />} />
                <Route path="/terms" element={<Terms />} />
                <Route path="/privacy" element={<Privacy />} />
                <Route path="/copyright" element={<CopyrightNotice />} />
                <Route element={<RequireAuth />}>
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/world/:novelId" element={<WorldModel />} />
                </Route>
              </Route>
              {/* Self-contained new pages */}
              <Route element={<RequireAuth />}>
                <Route path="/library" element={<LibraryPage />} />
                <Route path="/novel/:novelId" element={<NovelDetailPage />} />
                <Route path="/novel/:novelId/chapter/:chapterNum/write" element={<WritingWorkspace />} />
                <Route path="/novel/:novelId/chapter/:chapterNum/results" element={<GenerationResults />} />
              </Route>
              {/* Login (standalone) */}
              <Route path="/login" element={<Login />} />
            </Routes>
          </Suspense>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
