import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type QueueForecast = S["QueueForecastOut"];
export type VesselInPort = S["VesselInPortOut"];
export type VesselTrack = S["VesselTrackOut"];
export type Meta = S["Meta"];
export type Snapshot = { forecast: QueueForecast; vessels: VesselInPort[]; meta: Meta };

export const CARGO = new Set(["cargo", "container", "dry_bulk", "general_cargo", "tanker"]);

/** Hours as "2.3 d" or "17 h". */
export function span(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  return h >= 48 ? `${(h / 24).toFixed(1)} d` : `${Math.round(h)} h`;
}

/** Was the actual departure inside the P10–P90 band? */
export function inBand(v: VesselInPort): boolean | null {
  if (!v.actual_departure_ts) return null;
  const t = Date.parse(v.actual_departure_ts);
  return t >= Date.parse(v.departure_p10) && t <= Date.parse(v.departure_p90);
}
