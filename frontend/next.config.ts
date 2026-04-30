import type { NextConfig } from "next";

// Single-service deploy: backend (FastAPI) Railway'de hem API hem static frontend serve eder.
// Bu yüzden output: 'export' static HTML üretiyoruz, runtime rewrites/proxy gerekmez.
const config: NextConfig = {
  output: "export",
  reactStrictMode: true,
  trailingSlash: false,
  images: { unoptimized: true },
  experimental: {
    optimizePackageImports: ["recharts"],
  },
};

export default config;
