import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const packageJson = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'),
) as { version?: unknown }

if (typeof packageJson.version !== 'string' || packageJson.version.trim() === '') {
  throw new Error('web/package.json must define a non-empty version')
}

const buildId = (
  process.env.NOVWR_BUILD_ID
  ?? process.env.VERCEL_GIT_COMMIT_SHA
  ?? process.env.GITHUB_SHA
  ?? new Date().toISOString()
).trim()

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: { license: { fileName: 'THIRD-PARTY-LICENSES.md' } },
  define: {
    __NOVWR_APP_VERSION__: JSON.stringify(packageJson.version),
    __NOVWR_BUILD_ID__: JSON.stringify(buildId),
  },
  resolve: {
    alias: {
      '@': path.resolve(path.dirname(fileURLToPath(import.meta.url)), './src'),
    },
  },
  // Dev-only: proxy API calls to the FastAPI backend so Windows->WSL browser sessions
  // can use same-origin `/api/*` without fighting CORS or env wiring.
  server: {
    host: true,
    proxy: {
      '/api': {
        target: process.env.NOVWR_DEV_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
