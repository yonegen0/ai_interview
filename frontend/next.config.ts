import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  distDir: process.env.POCKET_MOCK_BUILD === "true" ? "out-mock" : ".next",
};

if (
  process.env.NODE_ENV === "production" &&
  process.env.NEXT_PUBLIC_MSW_ENABLED === "true" &&
  process.env.POCKET_MOCK_BUILD !== "true"
) {
  throw new Error("Mock production build requires npm run build:mock");
}

export default nextConfig;
