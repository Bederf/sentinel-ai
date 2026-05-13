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
    target: 'es2022',
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        kiosk: resolve(__dirname, 'kiosk.html'),
      },
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined

          // Heavy 3D dependencies — only loaded when 3D components render
          if (id.includes('three-stdlib') || id.includes('OrbitControls')) return 'vendor-3d-controls'
          if (id.includes('@react-three/fiber') || id.includes('/three/')) return 'vendor-3d-core'
          if (id.includes('@react-three/drei')) return 'vendor-3d-drei'

          // Visualization
          if (id.includes('cytoscape')) return 'vendor-graph'

          // Tremor (UI components)
          if (id.includes('@tremor/react')) return 'vendor-tremor'

          // Drag-and-drop
          if (id.includes('@dnd-kit/')) return 'vendor-dnd'

          // Animation libraries — lazy loaded
          if (id.includes('gsap')) return 'vendor-animation'
          if (id.includes('framer-motion')) return 'vendor-motion'

          // Let rollup naturally chunk everything else by package
          // This avoids circular chunk dependencies that cause TDZ errors
          return undefined
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'lucide-react'],
    exclude: ['@react-three/fiber', '@react-three/drei', 'three'],
  },
})
