"use server";

import { api } from "@/lib/api/server";

export type Management = Record<string, string | null>;

/** Owner, manager, class and P&I of a real ship (DataDocked; 3 trial credits, cached a year). */
export async function lookUpManagement(mmsi: number): Promise<{ data?: Management; error?: string }> {
  const client = await api();
  const { data, error, response } = await client.POST("/api/v1/ships/{mmsi}/management", {
    params: { path: { mmsi } },
  });
  if (data) return { data: data.data as Management };
  const detail = (error as { detail?: string } | undefined)?.detail;
  return { error: detail ?? `lookup failed (${response.status})` };
}
