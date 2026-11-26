import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'

const hostname = process.env.PWA_TEST_HOSTNAME
if (hostname && !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+ts\.net$/.test(hostname)) {
  throw new Error('PWA_TEST_HOSTNAME must be an exact Tailscale hostname')
}

const codespaceName = process.env.CODESPACE_NAME
if (codespaceName && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(codespaceName)) {
  throw new Error('Invalid CODESPACE_NAME')
}

const allowedHosts = hostname ? [hostname] : []
if (codespaceName) {
  allowedHosts.push(`${codespaceName}-5174.app.github.dev`)
}

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts,
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
