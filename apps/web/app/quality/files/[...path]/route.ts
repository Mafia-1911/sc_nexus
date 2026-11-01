import { apiBase } from "@/lib/api/server";

/** Gallery thumbnails, heatmaps and uploads, proxied from the API (the browser never calls it). */
export async function GET(_req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (!path.length || path.some((p) => p === ".." || p.includes("/"))) return new Response("not found", { status: 404 });
  const upstream = await fetch(`${apiBase()}/api/v1/quality/files/${path.map(encodeURIComponent).join("/")}`, { cache: "no-store" });
  if (!upstream.ok || !upstream.body) return new Response("not found", { status: 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": "public, max-age=86400",
    },
  });
}
