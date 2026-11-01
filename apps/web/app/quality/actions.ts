"use server";

import { api, apiBase } from "@/lib/api/server";
import type { Item, LiveResult, LotDetail, Spc } from "@/lib/c5";

/** Server actions: the browser never calls the REST API itself (ADR-015). */
export async function loadLot(id: string, scenario: string): Promise<LotDetail | null> {
  const client = await api();
  const { data } = await client.GET("/api/v1/quality/batches/{batch_id}", {
    params: { path: { batch_id: id }, query: { scenario } },
  });
  return data?.data ?? null;
}

export async function loadSpc(lineId: string, scenario: string): Promise<Spc | null> {
  const client = await api();
  const { data } = await client.GET("/api/v1/quality/lines/{line_id}/spc", {
    params: { path: { line_id: lineId }, query: { scenario } },
  });
  return data?.data ?? null;
}

export async function loadGallery(category: string): Promise<Item[]> {
  const client = await api();
  const { data } = await client.GET("/api/v1/quality/gallery", { params: { query: { category, limit: 24 } } });
  return data?.data ?? [];
}

export async function inspectImage(form: FormData): Promise<{ data?: LiveResult; error?: string }> {
  const file = form.get("image");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose an image first." };
  if (file.size > 10 * 1024 * 1024) return { error: "The image is larger than 10 MB." };
  const body = new FormData();
  body.set("image", file, file.name);
  body.set("category", String(form.get("category") ?? "stitch"));
  const res = await fetch(`${apiBase()}/api/v1/quality/inspections`, { method: "POST", body, cache: "no-store" });
  const json = (await res.json().catch(() => ({}))) as { data?: LiveResult; detail?: string };
  return res.ok && json.data ? { data: json.data } : { error: json.detail ?? `Inspection failed (HTTP ${res.status}).` };
}
