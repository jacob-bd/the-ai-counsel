import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Ports live in the repo-root .env so backend and frontend read the same values.
  const env = loadEnv(mode, path.resolve(import.meta.dirname, '..'), '')

  const frontendPort = Number(env.PORT_FRONTEND) || 5173
  const backendPort = Number(env.PORT_BACKEND) || 8001

  return {
    plugins: [react()],
    server: {
      port: frontendPort,
      strictPort: true,
    },
    preview: {
      port: frontendPort,
      strictPort: true,
    },
    define: {
      __BACKEND_PORT__: JSON.stringify(String(backendPort)),
    },
  }
})
