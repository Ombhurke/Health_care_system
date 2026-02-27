import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
  },
  optimizeDeps: {
    include: ['lucide-react', 'framer-motion', 'react-hook-form', 'zod', '@supabase/supabase-js']
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'ui-vendor': ['lucide-react', 'framer-motion', 'recharts'],
          'supabase-vendor': ['@supabase/supabase-js']
        }
      }
    }
  }
})
