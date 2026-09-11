/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import {
  applyPerformanceModeToDocument,
  applyRouteSurfaceToDocument,
  persistPerformanceMode,
  readPerformanceModeFromSearch,
  readStoredPerformanceMode,
  resolveRouteSurface,
  type PerformanceMode,
  type RouteSurfaceKind,
} from '@/lib/performanceMode'

type PerformanceModeContextValue = {
  mode: PerformanceMode
  isLite: boolean
  routeSurface: RouteSurfaceKind
  showAmbientBackground: boolean
}

const PerformanceModeContext = createContext<PerformanceModeContextValue | undefined>(undefined)

export function PerformanceModeProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const routeSurface = resolveRouteSurface(location.pathname)
  const searchMode = readPerformanceModeFromSearch(location.search)
  const storedMode: PerformanceMode = routeSurface === 'workspace' ? readStoredPerformanceMode() : 'default'
  const mode: PerformanceMode = searchMode ?? storedMode

  useEffect(() => {
    applyPerformanceModeToDocument(mode)
  }, [mode])

  useEffect(() => {
    if (searchMode === null) return
    persistPerformanceMode(searchMode)
  }, [searchMode])

  useEffect(() => {
    applyRouteSurfaceToDocument(routeSurface)
  }, [routeSurface])

  const value = useMemo<PerformanceModeContextValue>(
    () => ({
      mode,
      isLite: mode === 'lite',
      routeSurface,
      // Landing (`/`) uses the lattice stage — no ambient blobs. Other marketing
      // surfaces (login/legal) keep the ambient layer when performance allows.
      showAmbientBackground: mode !== 'lite' && routeSurface === 'marketing' && location.pathname !== '/',
    }),
    [mode, routeSurface, location.pathname],
  )

  return (
    <PerformanceModeContext.Provider value={value}>
      {children}
    </PerformanceModeContext.Provider>
  )
}

export function usePerformanceMode() {
  const context = useContext(PerformanceModeContext)
  if (context === undefined) {
    throw new Error('usePerformanceMode must be used within a PerformanceModeProvider')
  }
  return context
}
