import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // Port 8080 matches the API's default CORS origins.
  server: { port: 8080, strictPort: true },
  preview: { port: 8080, strictPort: true },
  test: {
    environment: "happy-dom",
    // tests/chatApi.test.mjs uses node:test and runs separately.
    include: ["tests/**/*.spec.js"],
  },
});
