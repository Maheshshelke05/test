import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// WEB_SUBPATH=admin builds for https://host/admin/ (see deploy/deploy.sh).
const subpath = (process.env.WEB_SUBPATH || '').replace(/^\/+|\/+$/g, '')

export default defineConfig({
  plugins: [react()],
  base: subpath ? `/${subpath}/` : '/',
  server: { port: 3000, host: true },
})
