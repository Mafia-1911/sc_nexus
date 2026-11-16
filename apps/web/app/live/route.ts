import { apiBase, apiHeaders } from "@/lib/api/server";

/** Live vessel positions for hosts without browser WebSockets (the deployed site): the same
 *  message as /ws/live, fetched server-side so the API token stays here (A-117). */
export async function GET(req: Request) {
  const scenario = new URL(req.url).searchParams.get("scenario") ?? "baseline";
  const upstream = await fetch(`${apiBase()}/api/v1/live?scenario=${encodeURIComponent(scenario)}`, {
    cache: "no-store",
    headers: apiHeaders(),
  });
  if (!upstream.ok) return new Response("unavailable", { status: 502 });
  return new Response(upstream.body, { headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
