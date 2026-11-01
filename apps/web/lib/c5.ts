import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type Lot = S["LotOut"];
export type LotDetail = S["LotDetailOut"];
export type Item = S["ItemOut"];
export type Line = S["LineOut"];
export type Spc = S["SpcOut"];
export type LiveResult = S["LiveResultOut"];
export type LotOption = S["LotOptionOut"];
export type Meta = S["Meta"];

/** Images and heatmaps come through this app (never straight from the API, ADR-015). */
export const fileUrl = (uri: string | null | undefined) => (uri ? `/quality/files/${uri}` : "");

export const STATUS: Record<string, { label: string; tone: "ok" | "danger" | "warn" | "info" | "neutral" }> = {
  released: { label: "Released", tone: "ok" },
  rejected: { label: "Rejected", tone: "danger" },
  quarantine: { label: "QA review", tone: "warn" },
  rework: { label: "Rework", tone: "info" },
  in_process: { label: "Awaiting QC", tone: "neutral" },
};

export const ACTION: Record<string, string> = {
  rework: "Rework (100 % inspection and repair)",
  replace_production: "Replace: make the lot again",
  expedite_air: "Expedite by air",
  notify_customer: "Notify the buyer",
  reinspect: "QA re-inspection",
  hold_shipment: "Hold the shipment",
};

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v < 0 ? "−" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })}`;
}
