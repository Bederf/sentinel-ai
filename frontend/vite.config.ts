import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),   // existing React app
        kiosk: resolve(__dirname, 'kiosk.html'),  // new kiosk display
      },
    },
  },
})
