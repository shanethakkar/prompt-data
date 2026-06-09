import type { NextConfig } from "next";

// Proxy /api/* to the FastAPI backend so the browser stays same-origin (no CORS, SSE works
// through the dev server). Override the target with API_BASE for deploy (Phase 6).
const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_BASE}/:path*` }];
  },
};

export default nextConfig;
