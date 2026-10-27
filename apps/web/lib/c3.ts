import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type RouteIn = S["RouteIn"];
export type RouteResult = S["RouteResult"];
export type Plan = S["PlanOut"];
export type Leg = S["LegOut"];
export type Place = { key: string; name: string; kind: string; lat: number; lon: number };

/** Mode colours use the chart slots (validated in both themes, 05 §2); a legend always shows. */
export const MODE_VAR: Record<string, string> = { road: "--series-1", rail: "--series-3", barge: "--series-4" };

export function taka(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `Tk ${v.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })}`;
}
