import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 9096,
    host: '0.0.0.0',
    allowedHosts: ['bms.aimthelaw.co.za', 'localhost'],
    proxy: {
      '/api': {
        target: 'http://localhost:9095',
        changeOrigin: true,
      },
    },
  },
})
