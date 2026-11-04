import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: the React app runs on :5173 and calls the FastAPI backend on :8000 through /api.
// Prod: FastAPI serves the built app from frontend/dist, so the frontend always calls relative /api.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    chunkSizeWarningLimit: 1600,
  },
})
