import "server-only";

import { cookies } from "next/headers";
import { connection } from "next/server";

export const SCENARIOS = [
  { key: "cyclone_supplier_delay", label: "Hero: Cyclone SYN-01 + Mill X delay" },
  { key: "baseline", label: "Baseline world" },
  { key: "", label: "Real data only" },
] as const;

export const DEFAULT_SCENARIO = "cyclone_supplier_delay";

/** The scenario whose synthetic rows are shown next to the real ones (cookie `scenario`). */
export async function currentScenario(): Promise<string> {
  await connection();
  const value = (await cookies()).get("scenario")?.value;
  return value === undefined ? DEFAULT_SCENARIO : value;
}
