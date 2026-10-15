import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import path from "node:path";

// Share the repo-root .env with FastAPI and local scripts.
loadEnvConfig(path.resolve(process.cwd(), ".."));

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{
      source: "/sw.js",
      headers: [
        { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        { key: "Content-Type", value: "application/javascript; charset=utf-8" },
      ],
    }];
  },
};

export default nextConfig;
