/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    typedRoutes: false,
  },
  webpack: (config, { dev }) => {
    // Docker bind mount: natív file watch helyett poll → kevesebb félbeszakadt chunk (HMR).
    if (dev && process.env.WATCHPACK_POLLING !== "false") {
      config.watchOptions = {
        poll: Number(process.env.WATCHPACK_POLLING_MS) || 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
};

export default nextConfig;
