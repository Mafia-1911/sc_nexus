"use server";

import { api } from "@/lib/api/server";
import type { QueueForecast, Snapshot, VesselTrack } from "@/lib/c4";

/** Server actions: the browser never calls the REST API itself (ADR-015). */
export async function loadSnapshot(locode: string, asOf?: string): Promise<{ data?: Snapshot; error?: string }> {
  const client = await api();
  const query = asOf ? { as_of: asOf } : {};
  const [f, v] = await Promise.all([
    client.GET("/api/v1/ports/{locode}/forecast", { params: { path: { locode }, query } }),
    client.GET("/api/v1/ports/{locode}/predictions", { params: { path: { locode }, query } }),
  ]);
  if (!f.data || !v.data) return { error: "No C4 predictions yet: run `uv run c4 train`." };
  // Tuples come back as plain arrays in the generated response type.
  return { data: { forecast: f.data.data as unknown as QueueForecast, vessels: v.data.data, meta: v.data.meta } };
}

export async function loadTrack(vesselId: string, asOf: string): Promise<VesselTrack | null> {
  const client = await api();
  const { data } = await client.GET("/api/v1/vessels/{vessel_id}/prediction", {
    params: { path: { vessel_id: vesselId }, query: { as_of: asOf } },
  });
  return data?.data ?? null;
}
