import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type EventItem = S["EventOut"];
export type EventDetail = S["EventDetailOut"];
export type Mention = S["MentionOut"];
export type AlertItem = S["AlertOut"];
export type Rec = S["RecommendationOut"];

export function typeName(type: string): string {
  return type.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export function hours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  return h >= 48 ? `${Math.round(h / 24)} d` : `${Math.round(h)} h`;
}

/** Split text into plain and highlighted parts from [start, end, quote] spans (C2 §9). */
export function highlight(text: string, spans: Record<string, unknown[]>): { text: string; mark: string | null }[] {
  const marks = Object.entries(spans)
    .map(([field, s]) => ({ field, start: Number(s[0]), end: Number(s[1]) }))
    .filter((m) => m.start >= 0 && m.end <= text.length && m.end > m.start)
    .sort((a, b) => a.start - b.start);
  const out: { text: string; mark: string | null }[] = [];
  let at = 0;
  for (const m of marks) {
    if (m.start < at) continue; // overlapping spans: keep the first
    if (m.start > at) out.push({ text: text.slice(at, m.start), mark: null });
    out.push({ text: text.slice(m.start, m.end), mark: m.field.replace(/_\d+$/, "").replaceAll("_", " ") });
    at = m.end;
  }
  if (at < text.length) out.push({ text: text.slice(at), mark: null });
  return out;
}
