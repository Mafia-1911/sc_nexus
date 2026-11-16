import { apiBase, apiHeaders } from "@/lib/api/server";

/** Keep-alive (Vercel cron, daily): a free Hugging Face Space sleeps after 48 h without
 *  requests; this wakes the API and reports whether it answered. */
export async function GET() {
  const t0 = Date.now();
  const res = await fetch(`${apiBase()}/health`, { cache: "no-store", headers: apiHeaders() }).catch(() => null);
  return Response.json({ web: "ok", api: res?.ok ? "ok" : "down", ms: Date.now() - t0 }, { status: res?.ok ? 200 : 503 });
}
