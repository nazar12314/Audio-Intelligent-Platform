import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const apiUrl = process.env.API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // The bucket CORS rules allow exactly this origin.
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiUrl,
      '/health': apiUrl,
    },
  },
  test: {
    environment: 'node',
  },
})
