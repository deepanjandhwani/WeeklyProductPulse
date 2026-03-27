import type { NextConfig } from "next";

const upstream =
  process.env.PULSE_API_UPSTREAM?.replace(/\/$/, "") ||
  "https://weeklyproductpulse.onrender.com";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${upstream}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
