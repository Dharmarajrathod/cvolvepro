import type { NextConfig } from "next";

const isGithubPages = process.env.GITHUB_PAGES === "true";
const isRenderStaticSite = process.env.RENDER === "true";
const isStaticExport = isGithubPages || isRenderStaticSite;
const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL;

const nextConfig: NextConfig = {
  output: isStaticExport ? "export" : "standalone",
  basePath: isGithubPages ? "/cvolvepro" : "",
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["127.0.0.1"],
  ...(!isStaticExport && backendUrl ? {
    async rewrites() {
      return [
        {
          source: "/api/:path*",
          destination: `${backendUrl.replace(/\/$/, "")}/api/:path*`,
        },
        {
          source: "/health",
          destination: `${backendUrl.replace(/\/$/, "")}/health`,
        },
      ];
    },
  } : {}),
};

export default nextConfig;
