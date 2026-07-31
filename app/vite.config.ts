import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { assetsInlineLimit: 1024 * 1024 },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
})
