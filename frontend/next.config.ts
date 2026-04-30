import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const config: NextConfig = {
  reactStrictMode: true,
  // Proxy /api/* to backend so cookies stay on a single origin (Vercel domain).
  // WebSocket /ws also proxied; Vercel supports WS proxying.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/ws", destination: `${apiUrl}/ws` },
      { source: "/healthz", destination: `${apiUrl}/healthz` },
    ];
  },
  experimental: {
    optimizePackageImports: ["recharts"],
  },
};

export default config;
