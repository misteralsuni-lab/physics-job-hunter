/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // NOTE: `output: "standalone"` would trim the production node_modules and
  // lower runtime RSS, but it requires symlink creation (copyTracedFiles)
  // which fails with EPERM on Windows without admin/Developer Mode.  Re-enable
  // only on the Linux deploy target (the systemd host documented in AGENTS.md).

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
