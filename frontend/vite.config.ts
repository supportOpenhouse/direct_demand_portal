import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// envDir '..' → the single root .env feeds both backend and frontend
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: { port: 5173 },
});
