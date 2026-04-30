import type { NextConfig } from "next";

// Single-service deploy: backend (FastAPI) Railway'de hem API hem static frontend serve eder.
// Bu yüzden output: 'export' static HTML üretiyoruz, runtime rewrites/proxy gerekmez.
const config: NextConfig = {
  output: "export",
  reactStrictMode: true,
  // trailingSlash:true → routes export to /<route>/index.html (e.g. login/index.html).
  // FastAPI StaticFiles(html=True) otomatik index.html serve eder, ekstra handler gerekmez.
  trailingSlash: true,
  images: { unoptimized: true },
  experimental: {
    optimizePackageImports: ["recharts"],
  },
};

export default config;
