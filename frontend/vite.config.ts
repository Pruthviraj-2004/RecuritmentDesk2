/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

// The browser only ever talks to same-origin /api; Vite proxies it to the FastAPI backend in development.
// No secrets are read here: nothing prefixed VITE_ is used for credentials.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173, proxy: { "/api": { target: process.env.BACKEND_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: false } } },
  preview: { port: 4173 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"], css: false, exclude: ["e2e/**", "node_modules/**"] },
});
