import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type GraphNode = S["GraphNodeOut"];
export type GraphEdge = S["GraphEdgeOut"];
export type SupplyGraph = S["SupplyGraphOut"];
export type NodeMetrics = S["NodeMetrics"];
export type Critical = S["CriticalOut"];
export type NodeDetail = S["NodeDetailOut"];
export type WhatIf = S["WhatIfOut"];
export type WhatIfRequest = S["WhatIfRequest"];
export type DisruptionIn = S["DisruptionIn"];
export type Meta = S["Meta"];

export type Metric = "dominance" | "downstream" | "tts_gap" | "risk";
export const METRICS: { key: Metric; label: string }[] = [
  { key: "dominance", label: "Single points of failure" },
  { key: "tts_gap", label: "TTS vs TTR" },
  { key: "risk", label: "Risk score" },
];

/** Risk bands use the semantic tokens; colour is never the only cue (labels and legend). */
export const BAND_VAR: Record<string, string> = { high: "--danger", medium: "--warn", low: "--border-strong" };
export const BAND_TONE: Record<string, "danger" | "warn" | "neutral"> = { high: "danger", medium: "warn", low: "neutral" };

const TYPE_LABEL: Record<string, string> = {
  gateway: "Sea gateway",
  hub: "Transshipment hub",
  garment_factory: "Garment factory",
  fabric_mill: "Fabric mill",
  spinning_mill: "Spinning mill",
  trims_supplier: "Trims supplier",
  raw_material_supplier: "Overseas supplier",
  api_manufacturer: "API maker",
  excipient_supplier: "Excipient supplier",
  packaging_supplier: "Packaging supplier",
  pharma_plant: "Pharma plant",
  customer_site: "Buyer DC",
};

export function typeLabel(type: string, country?: string | null): string {
  if (type === "api_manufacturer" && country && country !== "BD") return "Overseas supplier";
  return TYPE_LABEL[type] ?? type.replaceAll("_", " ");
}

/** US$ with a compact suffix: 18.9M, 950k. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `US$${value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })}`;
}

export function days(value: number | null | undefined, capped = false): string {
  if (value === null || value === undefined) return "—";
  return `${capped ? "≥ " : ""}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })} d`;
}

export function productName(sku: string): string {
  return sku.replace(/^[GP]-/, "").replaceAll("_", " ").toLowerCase();
}
