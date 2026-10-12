import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  devIndicators: false,
  // Served under a path prefix behind nginx (e.g. /videoanalyzer). Empty for local dev.
  // Inlined at build time, so it is a Docker build arg.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
  // Only the Docker image uses the self-contained server; `next start` needs the default.
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
};

export default nextConfig;
