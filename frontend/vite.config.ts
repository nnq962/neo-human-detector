import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const apiBase = env.VITE_API_BASE_URL ?? "http://localhost:9721"
  const wsBase = apiBase.replace(/^http/, "ws")

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    resolve: {
      tsconfigPaths: true,
    },
    optimizeDeps: {
      include: ["fabric"],
    },
    server: {
      host: "0.0.0.0",
      proxy: {
        "/api": apiBase,
        "/ws": { target: wsBase, ws: true },
      },
    },
  }
})
