import type { NextConfig } from "next";

const apiOrigin = process.env.GRIDCAST_API_URL;
if (!apiOrigin) {
  throw new Error("GRIDCAST_API_URL must be set (for example, http://127.0.0.1:8000 locally).");
}

const nextConfig: NextConfig = {
  turbopack: { root: process.cwd() },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};
export default nextConfig;
