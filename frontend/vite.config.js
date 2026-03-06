import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:8000',  // http:// required — ws: true handles upgrade
        ws: true,
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
  }
})
