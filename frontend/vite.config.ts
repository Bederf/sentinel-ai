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
    allowedHosts: ['bms.aimthelaw.co.za', 'bms.aimthelaw.com', 'sentinel-ai.co.za', 'bms.sentinel-ai.co.za', 'localhost'],
    proxy: {
      '/api': {
        target: 'http://localhost:9095',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),   // existing React app
        kiosk: resolve(__dirname, 'kiosk.html'),  // new kiosk display
      },
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('three-stdlib') || id.includes('OrbitControls')) return 'vendor-3d-controls'
          if (id.includes('@react-three/fiber') || id.includes('/three/')) return 'vendor-3d-core'
          if (id.includes('@react-three/drei')) return 'vendor-3d-drei'
          if (id.includes('cytoscape')) return 'vendor-graph'
          if (id.includes('@tremor/react')) return 'vendor-tremor'
          if (id.includes('@dnd-kit/')) return 'vendor-dnd'
          return undefined
        },
      },
    },
  },
})
