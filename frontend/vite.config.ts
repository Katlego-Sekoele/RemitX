import { reactRouter } from "@react-router/dev/vite"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

export default defineConfig({
  // The repo keeps a single root .env for the API, the worker and this app,
  // so point Vite one level up instead of expecting a frontend/.env. Only
  // VITE_-prefixed vars are exposed to the client; the rest stay server-side.
  envDir: "..",
  resolve: { tsconfigPaths: true },
  plugins: [tailwindcss(), reactRouter()],
})
