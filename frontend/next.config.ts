import type { NextConfig } from "next";

const isGithubPages = process.env.GITHUB_ACTIONS === "true";

const nextConfig: NextConfig = {
  output: isGithubPages ? "export" : "standalone",
  basePath: isGithubPages ? "/cvolvepro" : "",
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
