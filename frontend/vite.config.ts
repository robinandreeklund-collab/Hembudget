import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 1420,
    strictPort: true,
    // Tillåt Cloudflare Tunnel-subdomäner (*.trycloudflare.com) så man kan
    // nå dev-servern från mobilen via `cloudflared tunnel`. Dessutom localhost-
    // varianter + LAN-IP-er via prefixet "." (matchar alla subdomäner).
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      ".trycloudflare.com",
      ".cfargotunnel.com",
    ],
  },
  clearScreen: false,
  envPrefix: ["VITE_", "TAURI_"],
});
