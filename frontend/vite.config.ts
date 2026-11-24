import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    // Honour PORT when the environment assigns one, otherwise 3000.
    // Vite does NOT read PORT by default — a bare `port: 3000` here silently
    // overrides whatever port a harness or host hands us, and the caller then
    // waits on a port nothing is listening on.
    port: Number(process.env.PORT) || 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
