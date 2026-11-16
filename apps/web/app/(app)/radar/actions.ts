"use server";

import { api } from "@/lib/api/server";
import type { EventDetail, Rec } from "@/lib/c2";

/** Server actions: the browser never calls the REST API itself (ADR-015). */
export async function loadEvent(scenario: string, eventId: string): Promise<{ data?: EventDetail; error?: string }> {
  const client = await api();
  const { data } = await client.GET("/api/v1/events/{event_id}", {
    params: { path: { event_id: eventId }, query: { scenario } },
  });
  return data ? { data: data.data } : { error: "Could not load the event." };
}

export async function decide(
  scenario: string,
  recId: string,
  decision: "accepted" | "dismissed",
  feedback: string | null,
): Promise<{ data?: Rec; error?: string }> {
  const client = await api();
  const { data } = await client.POST("/api/v1/recommendations/{rec_id}/decision", {
    params: { path: { rec_id: recId }, query: { scenario } },
    body: { decision, feedback },
  });
  return data ? { data: data.data } : { error: "The decision was not saved." };
}
