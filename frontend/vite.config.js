import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/generate': 'http://localhost:8000',
      '/export': 'http://localhost:8000',
      '/export-canvas': 'http://localhost:8000',
      '/image-proxy': 'http://localhost:8000',
      '/history': 'http://localhost:8000',
    }
  }
})
