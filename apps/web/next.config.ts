import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server for the compose `web` service (node .next/standalone/server.js).
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
