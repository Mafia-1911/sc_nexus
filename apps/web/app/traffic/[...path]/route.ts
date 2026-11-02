import { apiBase } from "@/lib/api/server";

/** The Route Planner's traffic layer, proxied from the API (the Mapbox token stays there). */
export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (!path.length || path.some((p) => p === ".." || p.includes("/"))) return new Response("not found", { status: 404 });
  const query = new URL(req.url).search;
  const upstream = await fetch(`${apiBase()}/api/v1/traffic/${path.map(encodeURIComponent).join("/")}${query}`, {
    cache: "no-store",
  });
  if (upstream.status === 204) return new Response(null, { status: 204 });
  if (!upstream.ok || !upstream.body) return new Response("not found", { status: upstream.status === 404 ? 404 : 502 });
  return new Response(upstream.body, {
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": upstream.headers.get("cache-control") ?? "no-store",
    },
  });
}
