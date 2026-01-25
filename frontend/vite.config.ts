import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['bms.aimthelaw.co.za', 'localhost'],
    proxy: {
      '/api': {
        target: 'http://localhost:9097',
        changeOrigin: true,
      },
    },
  },
})
