import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker: VITE_API_TARGET=http://api:8000 (set via docker-compose environment)
// Outside Docker: falls back to localhost
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    watch: {
      usePolling: true,   // required for Windows → Docker mounts (inotify doesn't work)
      interval: 300,
    },
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
