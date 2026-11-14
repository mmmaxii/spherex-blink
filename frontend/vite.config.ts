import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, /api goes to the local FastAPI server (same paths as production,
// where vercel.json rewrites /api to the Render service).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
