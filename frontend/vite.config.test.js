import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'

const hostname = process.env.PWA_TEST_HOSTNAME
if (hostname && !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+ts\.net$/.test(hostname)) {
  throw new Error('PWA_TEST_HOSTNAME must be an exact Tailscale hostname')
}

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: hostname ? [hostname] : [],
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
