import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev  : Vite sert le front sur http://localhost:5173/labo/ et relaie /api vers FastAPI (8770).
// Prod : `npm run build` produit dist/, servi par `uv run shadowlab site` sous /labo.
export default defineConfig({
  base: "/labo/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8770", changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
