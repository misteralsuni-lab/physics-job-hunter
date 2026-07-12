/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // `output: "standalone"` trims the production server bundle and lowers
  // runtime RSS, which keeps `pnpm start` alive on the <2 Gi RAM systemd host
  // (see AGENTS.md). It is safe here: the deploy target is Linux, where the
  // symlink creation that previously failed with EPERM on Windows is not an
  // issue. The lightweight static-preview path in AGENTS.md still works
  // against the prerendered output.
  output: "standalone",

  experimental: {
    // Tree-shake barrel-export libs at build time.  lucide-react ships
    // thousands of icons via a single index; this flag makes the bundler
    // resolve only the named imports actually used, cutting both build
    // memory (fewer AST nodes held simultaneously) and client bundle.
    optimizePackageImports: [
      "lucide-react",
      "@supabase/supabase-js",
    ],
  },
};

export default nextConfig;
