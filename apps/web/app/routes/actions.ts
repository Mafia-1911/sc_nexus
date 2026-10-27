"use server";

import { api } from "@/lib/api/server";
import type { RouteIn, RouteResult } from "@/lib/c3";

/** Server action: the browser never calls the REST API itself (ADR-015). */
export async function optimize(body: RouteIn): Promise<{ data?: RouteResult; error?: string }> {
  const client = await api();
  const { data, error } = await client.POST("/api/v1/routes/optimize", { body });
  if (data) return { data: data.data };
  return { error: (error as { detail?: string })?.detail ?? "Planning failed." };
}
