import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/orders': { target: 'http://localhost:8000', changeOrigin: true },
      '/products': { target: 'http://localhost:8000', changeOrigin: true },
      '/dashboard': { target: 'http://localhost:8000', changeOrigin: true },
      '/tickets': { target: 'http://localhost:8000', changeOrigin: true },
      '/reports': { target: 'http://localhost:8000', changeOrigin: true },
      '/auth':    { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: '../static/dashboard',
    emptyOutDir: true,
  },
})
