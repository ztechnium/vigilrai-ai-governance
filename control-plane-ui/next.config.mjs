/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow alternate output dirs when .next is not writable (e.g. root-owned CI artifacts).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async redirects() {
    return [
      { source: "/finops/usage", destination: "/finops#usage", permanent: false },
      { source: "/finops/models", destination: "/finops#models", permanent: false },
      { source: "/login", destination: "/", permanent: false },
      { source: "/administration/users", destination: "/organization/team", permanent: false },
    ];
  },
};

export default nextConfig;
