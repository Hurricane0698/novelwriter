import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
