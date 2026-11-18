import type { components } from "@/lib/api/types";
import { fmt } from "@/lib/utils";

type S = components["schemas"];
export type TariffOverview = S["OverviewOut"];
export type TariffCell = S["CellOut"];
export type TariffMatrix = S["MatrixOut"];
export type ProductDetail = S["ProductDetailOut"];
export type LineRate = S["LineRateOut"];
export type RateComponent = S["ComponentOut"];
export type TariffChange = S["ChangeOut"];
export type TradeNotice = S["NoticeOut"];
export type TariffNews = S["NewsOut"];
export type OriginDetail = S["OriginDetailOut"];

/** Markets the monitor watches, in the order the columns show them. EU is "EUN" (WITS code). */
export const MARKETS: { code: string; name: string; short: string }[] = [
  { code: "USA", name: "United States", short: "US" },
  { code: "GBR", name: "United Kingdom", short: "UK" },
  { code: "EUN", name: "European Union", short: "EU" },
  { code: "JPN", name: "Japan", short: "Japan" },
  { code: "CAN", name: "Canada", short: "Canada" },
];
export const MARKET_NAME: Record<string, string> = Object.fromEntries(MARKETS.map((m) => [m.code, m.name]));

const EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"];

/** A country (ISO2, as the supply graph stores it) → the tariff market that charges its imports. */
export function marketOf(iso2: string | null | undefined): string | null {
  if (!iso2) return null;
  const c = iso2.toUpperCase();
  if (EU27.includes(c)) return "EUN";
  return { US: "USA", GB: "GBR", JP: "JPN", CA: "CAN", BD: "BGD" }[c] ?? null;
}

/** "26.5%", "12%", "Free". */
export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v === 0) return "Free";
  return `${fmt(v, Number.isInteger(v) ? 0 : 1)}%`;
}

/** What a matrix cell says: one number, a range over national lines, a floor, or nothing. */
export function cellText(
  c: Pick<TariffCell, "effective_pct_min" | "effective_pct_max" | "is_resolved" | "base_pct" | "n_lines"> & { is_ceiling?: boolean },
): string {
  if (c.n_lines === 0) return "—";
  if (!c.is_resolved || c.effective_pct_max === null || c.effective_pct_max === undefined) {
    // no base number: national lines differ (an annual average); the cell's note gives the range
    return c.base_pct === null || c.base_pct === undefined ? "varies" : `≥ ${pct(c.base_pct).replace("Free", "0%")}`;
  }
  const lo = c.effective_pct_min ?? c.effective_pct_max;
  const text = lo === c.effective_pct_max ? pct(lo) : `${pct(lo).replace("Free", "0%")}–${pct(c.effective_pct_max)}`;
  // no preference data for this market: the most this origin pays (Free needs no bound)
  return c.is_ceiling && c.effective_pct_max > 0 ? `≤ ${text}` : text;
}

/** Ordinal tiers on the theme's depth ramp (Q-22): 0 is its own "free" tier, not a magnitude. */
export type Tier = "free" | 1 | 2 | 3 | 4 | 5;
export const TIERS: { tier: Tier; label: string }[] = [
  { tier: "free", label: "Free" },
  { tier: 1, label: "≤ 5%" },
  { tier: 2, label: "5–10%" },
  { tier: 3, label: "10–15%" },
  { tier: 4, label: "15–25%" },
  { tier: 5, label: "> 25%" },
];
export function tierOf(v: number | null | undefined): Tier | null {
  if (v === null || v === undefined) return null;
  if (v === 0) return "free";
  if (v <= 5) return 1;
  if (v <= 10) return 2;
  if (v <= 15) return 3;
  if (v <= 25) return 4;
  return 5;
}
/** Full class strings (Tailwind finds them in the source); ink validated ≥ 4.5:1 per tier. */
export const TIER_CLASS: Record<string, string> = {
  free: "bg-surface text-text border border-border",
  "1": "bg-depth-1 text-on-depth-1",
  "2": "bg-depth-2 text-on-depth-2",
  "3": "bg-depth-3 text-on-depth-3",
  "4": "bg-depth-4 text-on-depth-4",
  "5": "bg-depth-5 text-on-depth-5",
};

export const ROLE_LABEL: Record<string, string> = {
  base: "Base rate (MFN)",
  preference: "Preference",
  additional: "Surcharge",
  possible_exemption: "Possible exemption",
  not_applied: "Not applied",
  unresolved: "Not machine-readable",
};

export const NOTICE_KIND: Record<string, string> = {
  tariff_modification: "Tariff change",
  trade_remedy: "Trade remedy (AD/CVD)",
  exclusion: "Exclusion",
  other: "Other",
};

export const DIRECTION: Record<string, { label: string; tone: "warn" | "ok" | "info" | "neutral" }> = {
  raise: { label: "Raise", tone: "warn" },
  cut: { label: "Cut", tone: "ok" },
  exempt: { label: "Exemption", tone: "ok" },
  unknown: { label: "Direction unclear", tone: "neutral" },
};

/** Feed status → badge tone and words. */
export const FEED_LOOK: Record<string, { label: string; tone: "ok" | "info" | "warn" | "neutral" }> = {
  live: { label: "Live", tone: "ok" },
  manual: { label: "Hand-kept", tone: "warn" },
  missing: { label: "Missing", tone: "neutral" },
};

/** Column chip for a market: is its schedule live, an annual average, or hand-kept? */
export function marketSource(code: string, liveSource: string | null | undefined): { label: string; title: string } {
  if (liveSource) return { label: "live schedule", title: `Official schedule, refreshed daily (${liveSource})` };
  if (code === "EUN") return { label: "2023 · hand-kept prefs", title: "MFN: WITS 2023 average; preferences: hand-kept table, unverified" };
  return { label: "2023 MFN · no preference data", title: "MFN: WITS reported 2023 average; preferences (e.g. LDC duty-free access) not in the data, so a value is the most an origin pays" };
}

export function countryName(origins: { iso3: string; name: string }[], iso3: string): string {
  return origins.find((o) => o.iso3 === iso3)?.name ?? iso3;
}
