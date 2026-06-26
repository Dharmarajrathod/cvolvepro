import type { NextConfig } from "next";

const isGithubPages = process.env.GITHUB_PAGES === "true";
const isStaticExport = isGithubPages || process.env.RENDER === "true";

const nextConfig: NextConfig = {
  output: isStaticExport ? "export" : "standalone",
  basePath: isGithubPages ? "/cvolvepro" : "",
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
