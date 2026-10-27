"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { BAND_TONE, METRICS, type Metric, type NodeMetrics, days, typeLabel, usd } from "@/lib/c1";
import { cn } from "@/lib/utils";

function value(m: NodeMetrics, metric: Metric): string {
  if (metric === "risk") return m.risk_score === null || m.risk_score === undefined ? "—" : m.risk_score.toFixed(0);
  if (metric === "tts_gap") return `${days(m.tts_d, m.tts_capped)} / ${days(m.ttr_d)}`;
  return usd(m.dominated_value_usd);
}

/** Criticality leaderboard (C1-R01, C1-R03): what breaks most if it fails. */
export function Leaderboard({
  items,
  metric,
  industry,
  ttsBelowTtr,
  selected,
  onSelect,
}: {
  items: NodeMetrics[];
  metric: Metric;
  industry: string | null;
  ttsBelowTtr: string[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const below = new Set(ttsBelowTtr);
  const href = (m: Metric) => `?${new URLSearchParams({ ...(industry ? { industry } : {}), metric: m })}`;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <nav aria-label="Rank by" className="flex flex-wrap gap-1">
        {METRICS.map((m) => (
          <Link
            key={m.key}
            href={href(m.key)}
            scroll={false}
            aria-current={m.key === metric ? "page" : undefined}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs",
              m.key === metric ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text",
            )}
          >
            {m.label}
          </Link>
        ))}
      </nav>
      <ol className="flex min-h-0 flex-1 flex-col divide-y divide-border overflow-y-auto" data-testid="leaderboard">
        {items.map((m, i) => (
          <li key={m.node_id}>
            <button
              type="button"
              onClick={() => onSelect(m.node_id)}
              aria-pressed={m.node_id === selected}
              className={cn(
                "grid w-full grid-cols-[1.25rem_1fr_auto] items-start gap-x-2 px-1 py-2 text-left text-sm hover:bg-surface-2",
                m.node_id === selected && "bg-surface-2",
              )}
              data-node={m.node_id}
            >
              <span className="tabular pt-0.5 text-xs text-muted">{i + 1}</span>
              <span className="truncate font-medium" title={m.name}>
                {m.name}
              </span>
              {m.risk_band ? (
                <Badge tone={BAND_TONE[m.risk_band] ?? "neutral"}>{m.risk_band}</Badge>
              ) : (
                <span />
              )}
              <span />
              <span className="truncate text-xs text-muted">
                {typeLabel(m.type)}
                {m.dominated_orders ? ` · sole path for ${m.dominated_orders} orders` : ""}
                {below.has(m.node_id) ? " · TTS < TTR" : ""}
              </span>
              <span className="tabular text-right text-xs">{value(m, metric)}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
