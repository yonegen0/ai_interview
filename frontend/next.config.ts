import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  // Explicit local worktree build override permits a shared, unchanged dependency cache.
  turbopack: {
    root: process.env.POCKET_TURBOPACK_ROOT ?? path.resolve(__dirname, ".."),
  },
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
