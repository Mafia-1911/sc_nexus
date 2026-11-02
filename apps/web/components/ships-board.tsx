"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/types";
import { dhakaTime, fmt } from "@/lib/utils";

type Ship = components["schemas"]["ShipOut"];

const STATUS: Record<string, { label: string; tone: "info" | "warn" | "ok" | "neutral" }> = {
  expected: { label: "Expected", tone: "neutral" },
  at_anchorage: { label: "At anchorage", tone: "warn" },
  in_port: { label: "In port area", tone: "warn" },
  at_berth: { label: "At berth", tone: "ok" },
  departed: { label: "Departed", tone: "info" },
};

function hours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  return h >= 48 ? `${fmt(h / 24, 1)} d` : `${fmt(h)} h`;
}

/** Hover / focus card with everything known about the ship, and what has no source yet. */
function Details({ s }: { s: Ship }) {
  const rows: [string, string][] = [
    ["MMSI / IMO", `${s.mmsi ?? "—"} / ${s.imo ?? "—"}`],
    ["Flag · type", `${s.flag ?? "—"} · ${s.ship_type ?? "—"}`],
    ["Length · GT", `${s.loa_m ? `${fmt(s.loa_m)} m` : "—"} · ${s.gt ? fmt(s.gt) : "—"}`],
    ["Arrived", dhakaTime(s.arrival_ts)],
    ["Berthed", dhakaTime(s.berth_ts)],
    ["Left", dhakaTime(s.departure_ts)],
  ];
  const unknown = Object.entries(s.unknown ?? {});
  return (
    <div
      role="tooltip"
      className="invisible absolute left-0 top-full z-20 mt-1 w-80 rounded-[var(--radius-card)] border border-border bg-surface p-3 text-xs text-text opacity-0 shadow-lg transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
    >
      <p className="mb-1 text-sm font-semibold">{s.name ?? "Unnamed vessel"}</p>
      <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="tabular">{v}</dd>
          </div>
        ))}
      </dl>
      {unknown.length ? (
        <ul className="mt-2 border-t border-border pt-2 text-muted">
          {unknown.map(([k, why]) => (
            <li key={k}>
              <span className="capitalize">{k.replace("_", " ")}</span>: not available yet ({why})
            </li>
          ))}
        </ul>
      ) : null}
      {s.is_synthetic ? <p className="mt-2 text-warn">Synthetic vessel in a simulated port.</p> : null}
    </div>
  );
}

export function ShipsBoard({ ships, counts, real }: { ships: Ship[]; counts: Record<string, number>; real: boolean }) {
  const [filter, setFilter] = useState<string>("all");
  const keys = Object.keys(STATUS).filter((k) => counts[k]);
  const shown = filter === "all" ? ships : ships.filter((s) => s.status === filter);
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Filter by status" data-testid="ship-filters">
        {["all", ...keys].map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={filter === k}
            onClick={() => setFilter(k)}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${filter === k ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text"}`}
          >
            {k === "all" ? "All" : STATUS[k].label} {k === "all" ? ships.length : counts[k]}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="ships">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-medium">Ship</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Arrived</th>
              <th className="py-2 pr-3 font-medium">In port</th>
              <th className="py-2 pr-3 font-medium">Estimated dock time</th>
              <th className="py-2 pr-3 font-medium">Cargo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {shown.slice(0, 15).map((s) => (
              <tr key={s.call_id} data-testid="ship-row">
                <td className="py-2 pr-3">
                  <span className="group relative inline-block" tabIndex={0}>
                    <span className="cursor-help font-medium underline decoration-dotted underline-offset-2">
                      {s.name ?? `MMSI ${s.mmsi}`}
                    </span>
                    <Details s={s} />
                  </span>
                </td>
                <td className="py-2 pr-3">
                  <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
                </td>
                <td className="tabular py-2 pr-3 text-xs">{dhakaTime(s.arrival_ts)}</td>
                <td className="tabular py-2 pr-3 text-xs">{hours(s.hours_in_port)}</td>
                <td className="tabular py-2 pr-3 text-xs">
                  {s.status === "departed" ? (
                    <span className="text-muted">left {dhakaTime(s.departure_ts)}</span>
                  ) : s.dock_estimate ? (
                    <span title={s.dock_note ?? undefined}>
                      {dhakaTime(s.dock_estimate)}
                      {s.dock_p90 && s.dock_p90 !== s.dock_estimate ? (
                        <span className="text-muted"> (P90 {dhakaTime(s.dock_p90)})</span>
                      ) : null}
                    </span>
                  ) : (
                    <span className="text-muted" title={s.dock_note ?? undefined}>
                      not observable
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 text-xs">
                  {s.containers || (s.orders ?? []).length ? (
                    <span>
                      {s.containers ? `${s.containers} containers` : ""}
                      {(s.orders ?? []).length
                        ? ` · orders ${(s.orders ?? []).slice(0, 2).join(", ")}${(s.orders ?? []).length > 2 ? "…" : ""}`
                        : ""}
                    </span>
                  ) : (
                    <span className="text-muted" title={s.cargo_note ?? undefined}>
                      {real ? "not public" : "—"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length > 15 ? <p className="mt-1 text-xs text-muted">Showing 15 of {shown.length}.</p> : null}
    </div>
  );
}
