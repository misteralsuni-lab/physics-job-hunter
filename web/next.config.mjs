/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Trace only the deps actually imported and emit a self-contained
  // `.next/standalone/` server.  Reduces build working-set (no full
  // node_modules traversal) and cuts production RSS on low-memory hosts.
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
