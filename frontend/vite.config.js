import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/emct/',
  server: {
    proxy: {
      '/api': 'http://localhost:8017'
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
