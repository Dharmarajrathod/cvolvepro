import type { NextConfig } from "next";

const isGithubPages = process.env.GITHUB_PAGES === "true";
const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL;

const nextConfig: NextConfig = {
  output: isGithubPages ? "export" : "standalone",
  basePath: isGithubPages ? "/cvolvepro" : "",
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    if (!backendUrl || isGithubPages) return [];
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
};

export default nextConfig;
