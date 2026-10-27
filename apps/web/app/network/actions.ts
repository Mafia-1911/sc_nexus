"use server";

import { api } from "@/lib/api/server";
import type { NodeDetail, WhatIf, WhatIfRequest } from "@/lib/c1";

/** Server actions: the browser never calls the REST API itself (ADR-015). */
export async function loadNode(scenario: string, nodeId: string): Promise<{ data?: NodeDetail; error?: string }> {
  const client = await api();
  const { data, error } = await client.GET("/api/v1/graph/nodes/{node_id}", {
    params: { path: { node_id: nodeId }, query: { scenario } },
  });
  return data ? { data: data.data } : { error: (error as { detail?: string })?.detail ?? "Could not load the node." };
}

export async function runWhatIf(scenario: string, body: WhatIfRequest): Promise<{ data?: WhatIf; error?: string }> {
  const client = await api();
  const { data, error } = await client.POST("/api/v1/graph/whatif", { params: { query: { scenario } }, body });
  if (data && "data" in data) return { data: data.data };
  return { error: (error as { detail?: string })?.detail ?? "The what-if did not run." };
}
