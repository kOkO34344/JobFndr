import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker, nginx proxies /api to the backend service, so the app is
// same-origin. This proxy only exists for `npm run dev` on the host.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
