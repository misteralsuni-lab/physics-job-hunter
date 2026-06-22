// Next.js configuration for the Physics Job Hunter front end.
//
// Notes:
// - React strict mode surfaces latent side-effect bugs early.
// - The app is server-component first; the Supabase service-role key is only
//   ever imported inside modules guarded by `import "server-only"`.
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The pipeline control API routes spawn local processes; keep this app
  // buildable on any host (the routes themselves are no-ops off-Linux).
  experimental: {
    // Improve type-safety of server/client boundaries.
    typedRoutes: false,
  },
};

export default nextConfig;
