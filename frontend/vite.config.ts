import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// envDir '..' → the single root .env feeds both backend and frontend
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  // Dev proxies /v1 to the deployed Render API so the local UI sees real Gupshup
  // callbacks. It's a proxy rather than a direct cross-origin call because the API
  // refuses to boot in APP_ENV=prod with localhost in CORS_ORIGINS (assert_prod_safe),
  // so localhost can never be an allowed origin there. Same-origin → no CORS at all.
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: "https://direct-demand-api-7k48.onrender.com", changeOrigin: true },
    },
  },
});
