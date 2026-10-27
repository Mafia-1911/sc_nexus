"use client";

import { X } from "lucide-react";

import { WhatIfPanel } from "@/components/network/whatif-panel";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { BAND_TONE, type NodeDetail, type WhatIf, days, productName, typeLabel, usd } from "@/lib/c1";
import { fmt } from "@/lib/utils";

/** TTS vs TTR on one scale (C1-AC03): a TTS bar shorter than the TTR bar is the warning. */
function TtsTtr({ tts, ttr, capped, source }: { tts?: number | null; ttr?: number | null; capped?: boolean; source?: string | null }) {
  if (tts === null || tts === undefined || ttr === null || ttr === undefined) {
    return <p className="text-xs text-muted">No open orders depend on this node, so TTS and TTR are not computed.</p>;
  }
  const scale = Math.max(tts, ttr, 1);
  const short = !capped && tts < ttr;
  return (
    <div className="flex flex-col gap-1.5 text-xs" data-testid="tts-ttr">
      {[
        { label: "Time to survive", value: tts, text: days(tts, capped), color: short ? "var(--danger)" : "var(--ok)" },
        { label: `Time to recover (${source === "event" ? "from a linked event" : "prior, an estimate"})`, value: ttr, text: days(ttr), color: "var(--border-strong)" },
      ].map((row) => (
        <div key={row.label}>
          <div className="flex justify-between text-muted">
            <span>{row.label}</span>
            <span className="tabular text-text">{row.text}</span>
          </div>
          <div className="mt-0.5 h-2 rounded-full bg-surface-2">
            <div className="h-2 rounded-full" style={{ width: `${(Math.min(row.value, scale) / scale) * 100}%`, background: row.color }} />
          </div>
        </div>
      ))}
      <p className={short ? "text-danger" : "text-muted"}>
        {short
          ? "The network runs out before this node recovers."
          : "Buffers and alternative suppliers outlast the recovery time."}
      </p>
    </div>
  );
}

function Drivers({ drivers = [] }: { drivers?: NodeDetail["metrics"]["risk_drivers"] }) {
  const max = Math.max(1, ...drivers.map((d) => Math.abs(d.contribution)));
  return (
    <ul className="flex flex-col gap-1 text-xs" data-testid="risk-drivers">
      {drivers.map((d) => (
        <li key={d.feature} className="grid grid-cols-[1fr_7rem_3rem] items-center gap-2">
          <span className="truncate" title={d.label}>
            {d.label}
          </span>
          <span className="relative h-2 rounded-full bg-surface-2">
            <span
              className="absolute top-0 h-2 rounded-full"
              style={{
                left: d.contribution >= 0 ? "50%" : `${50 - (Math.abs(d.contribution) / max) * 50}%`,
                width: `${(Math.abs(d.contribution) / max) * 50}%`,
                background: d.contribution >= 0 ? "var(--danger)" : "var(--ok)",
              }}
            />
          </span>
          <span className="tabular text-right">{d.contribution >= 0 ? "+" : ""}{d.contribution.toFixed(1)}</span>
        </li>
      ))}
    </ul>
  );
}

export function NodeDrawer({
  detail,
  scenario,
  onClose,
  onResult,
}: {
  detail: NodeDetail;
  scenario: string;
  onClose: () => void;
  onResult: (result: WhatIf | null) => void;
}) {
  const m = detail.metrics;
  const inputs = Object.entries(detail.inputs);
  return (
    <Card className="grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid="node-drawer">
      <div className="flex flex-col gap-4">
        <header className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">{m.name}</h2>
            <p className="text-xs text-muted">
              {typeLabel(m.type)}
              {m.industry ? ` · ${m.industry}` : ""} · fictional firm, synthetic attributes
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close node details" className="rounded-[var(--radius-control)] p-1 text-muted hover:bg-surface-2">
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex items-center gap-3">
          <span className="tabular text-3xl font-semibold">{m.risk_score?.toFixed(0) ?? "—"}</span>
          <div className="text-xs text-muted">
            <span className="block">risk score (0–100, transparent baseline)</span>
            {m.risk_band ? <Badge tone={BAND_TONE[m.risk_band] ?? "neutral"}>{m.risk_band}</Badge> : null}
          </div>
        </div>
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted">Why: points against the average node</h3>
          <Drivers drivers={m.risk_drivers} />
        </section>
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted">Survive vs recover if it fails</h3>
          <TtsTtr tts={m.tts_d} ttr={m.ttr_d} capped={m.tts_capped} source={m.ttr_source} />
        </section>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <dt className="text-muted">Orders only it can stop</dt>
          <dd className="tabular">{fmt(m.dominated_orders)} · {usd(m.dominated_value_usd)}</dd>
          <dt className="text-muted">Orders that depend on it</dt>
          <dd className="tabular">{fmt(m.downstream_orders)} · {usd(m.downstream_open_order_value_usd)}</dd>
          <dt className="text-muted">Output lost over its TTR</dt>
          <dd className="tabular">{usd(m.performance_impact_usd)}</dd>
        </dl>
        {inputs.length ? (
          <section>
            <h3 className="mb-1.5 text-xs font-semibold text-muted">Inputs and their concentration (HHI)</h3>
            <ul className="flex flex-col gap-1 text-xs">
              {inputs.map(([sku, suppliers]) => (
                <li key={sku}>
                  <span className="font-medium">{productName(sku)}</span>{" "}
                  <span className="text-muted">
                    HHI {fmt(m.hhi_inputs[sku] ?? 0, 2)}
                    {suppliers.length === 1 ? " · single-sourced" : ""}:{" "}
                    {suppliers.map((s) => `${s.name} ${fmt(Number(s.share) * 100)}%`).join(", ")}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {detail.events.length ? (
          <section>
            <h3 className="mb-1.5 text-xs font-semibold text-muted">Linked open events</h3>
            <ul className="flex flex-col gap-1 text-xs">
              {detail.events.map((e) => (
                <li key={String(e.event_id)}>{String(e.title)}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {detail.dominated_orders.length ? (
          <section>
            <h3 className="mb-1.5 text-xs font-semibold text-muted">Orders with no other path</h3>
            <table className="w-full text-xs">
              <tbody>
                {detail.dominated_orders.slice(0, 6).map((o) => (
                  <tr key={String(o.order_id)} className="border-t border-border">
                    <td className="py-1 font-mono">{String(o.reference)}</td>
                    <td className="py-1">{productName(String(o.product))}</td>
                    <td className="tabular py-1 text-right">{usd(Number(o.revenue_usd))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {detail.dominated_orders.length > 6 ? (
              <p className="mt-1 text-xs text-muted">and {detail.dominated_orders.length - 6} more</p>
            ) : null}
          </section>
        ) : null}
      </div>
      <WhatIfPanel key={m.node_id} scenario={scenario} defaults={detail.whatif_defaults} nodeName={m.name} onResult={onResult} />
    </Card>
  );
}
