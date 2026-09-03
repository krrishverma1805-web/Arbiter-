/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // When a real API is configured, proxy /api/* to it. Otherwise the built-in
    // route handlers under src/app/api serve a frozen snapshot of a real run
    // (the hosted demo).
    const api = process.env.ARBITER_API_URL;
    return api ? [{ source: "/api/:path*", destination: `${api}/:path*` }] : [];
  },
};
export default nextConfig;
