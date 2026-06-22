// Server-only Supabase client.
//
// CRITICAL: This module imports `server-only`, which makes it a build-time
// error to import it from a Client Component. The service-role key bypasses
// Row-Level Security and therefore MUST NEVER reach the browser. All browser
// interactions go through route handlers that query Supabase here and return
// plain JSON.
import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let cached: SupabaseClient | null = null;

/**
 * Construct (and cache) a Supabase client using the service-role key.
 * Throws if the required environment variables are missing so callers can
 * catch and degrade gracefully — mirroring the Python back end's philosophy
 * of falling through to a local store on failure.
 */
export function getSupabaseServer(): SupabaseClient {
  if (cached) return cached;

  const url = process.env.SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !serviceRoleKey) {
    throw new Error(
      "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in web/.env.local.",
    );
  }

  cached = createClient(url, serviceRoleKey, {
    auth: {
      // No user sessions in this dashboard; the service role owns access.
      persistSession: false,
      autoRefreshToken: false,
    },
  });

  return cached;
}

/** Whether the Supabase environment variables are present. */
export function isSupabaseConfigured(): boolean {
  return Boolean(
    process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY,
  );
}
