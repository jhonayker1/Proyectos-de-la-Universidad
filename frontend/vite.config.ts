import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// En desarrollo, /api se redirige al backend FastAPI (sin problemas de CORS).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.BACKEND_URL || 'http://127.0.0.1:8000'
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': path.resolve(__dirname, './src') } },
    server: {
      port: 5173,
      proxy: {
        '/api': { target: backend, changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') },
      },
    },
  }
})
