import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// EVAS web UI. In dev, /api is proxied to the FastAPI backend (default :8000)
// so the browser can call the real endpoints without CORS config.
export default defineConfig({
  plugins: [react()],
  // Served under /app by FastAPI StaticFiles in production (see docs/ops.md).
  base: "/app/",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.EVAS_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
