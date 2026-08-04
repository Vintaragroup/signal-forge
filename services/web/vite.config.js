import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local HMR mode the Vite dev server proxies /api to the api service,
// mirroring what nginx does in deployed environments. The frontend always
// calls the same-origin /api path, so the code is identical in both modes.
const apiProxyTarget = process.env.API_PROXY_TARGET || "http://api:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
