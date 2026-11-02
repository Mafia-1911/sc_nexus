import "server-only";

import { cookies } from "next/headers";
import { connection } from "next/server";

/** Synthetic worlds (fictional firms, simulated port), shown only when picked. */
export const SCENARIOS = [
  { key: "baseline", label: "Normal operations" },
  { key: "cyclone_supplier_delay", label: "Cyclone shuts Chattogram + denim mill flood" },
] as const;

/** Real data at a moment: today is a nowcast, tomorrow a forecast. */
export const REAL_DAYS = [
  { key: "today", label: "Today (estimated)" },
  { key: "yesterday", label: "Yesterday" },
  { key: "tomorrow", label: "Tomorrow (forecast)" },
] as const;

/** Real data by default; a synthetic scenario only when the user picks one. */
export const DEFAULT_SCENARIO = "";

/** The scenario whose synthetic rows are shown (cookie `scenario`; "" = real data only). */
export async function currentScenario(): Promise<string> {
  await connection();
  const value = (await cookies()).get("scenario")?.value;
  return value === undefined ? DEFAULT_SCENARIO : value;
}

/** Real-data view time (cookie `asof`): today, yesterday, tomorrow or YYYY-MM-DD. */
export async function currentAsOf(): Promise<string> {
  await connection();
  const value = (await cookies()).get("asof")?.value ?? "today";
  return /^(today|yesterday|tomorrow|\d{4}-\d{2}-\d{2})$/.test(value) ? value : "today";
}
