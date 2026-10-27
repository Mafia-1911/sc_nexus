"use client";

import { Play } from "lucide-react";
import { useState, useTransition } from "react";

import { runWhatIf } from "@/app/network/actions";
import { type DisruptionIn, type WhatIf, days, productName, usd } from "@/lib/c1";
import { fmt } from "@/lib/utils";

/** Shortfall over time: the value of output plants could not make, by day. */
function Timeline({ result }: { result: WhatIf }) {
  const points = result.timeline.map((t) => ({ day: Number(t.day), value: Number(t.shortfall_value_usd) }));
  const width = 320;
  const height = 72;
  const maxDay = Math.max(30, ...points.map((p) => p.day));
  const maxValue = Math.max(1, ...points.map((p) => p.value));
  const x = (d: number) => (d / maxDay) * width;
  const y = (v: number) => height - (v / maxValue) * (height - 6);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const peak = Math.max(0, ...points.map((p) => p.value));
  const marks = [
    { day: result.first_impact_d, label: "first impact", color: "var(--danger)" },
    { day: result.recovery_d, label: "recovered", color: "var(--ok)" },
  ].filter((m): m is { day: number; label: string; color: string } => m.day !== null && m.day !== undefined);
  return (
    <figure className="flex flex-col gap-1">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-20 w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]"
        role="img"
        aria-label={`Peak shortfall ${usd(peak)} of output per day; first impact day ${result.first_impact_d ?? "none"}, recovered day ${result.recovery_d ?? "not within the horizon"}`}
      >
        {peak > 0 ? (
          <path d={`${path} L${x(points.at(-1)?.day ?? 0)},${height} L0,${height} Z`} fill="var(--danger)" fillOpacity={0.18} stroke="var(--danger)" strokeWidth={1.5} />
        ) : (
          <line x1={0} x2={width} y1={height - 1} y2={height - 1} stroke="var(--border-strong)" />
        )}
        {marks.map((m) => (
          <line key={m.label} x1={x(m.day)} x2={x(m.day)} y1={0} y2={height} stroke={m.color} strokeDasharray="3 3" />
        ))}
      </svg>
      <figcaption className="flex justify-between text-[11px] text-muted">
        <span>day 0 (scenario start)</span>
        <span>shortfall in output value, peak {usd(peak)}</span>
        <span>day {maxDay}</span>
      </figcaption>
    </figure>
  );
}

export function WhatIfPanel({
  scenario,
  defaults,
  nodeName,
  onResult,
}: {
  scenario: string;
  defaults: DisruptionIn;
  nodeName: string;
  onResult: (result: WhatIf | null) => void;
}) {
  const [form, setForm] = useState({
    duration_d: defaults.duration_d,
    capacity_pct: defaults.capacity_pct ?? 0,
    extra_lead_time_d: defaults.extra_lead_time_d ?? 0,
  });
  const [result, setResult] = useState<WhatIf | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const run = () =>
    start(async () => {
      setError(null);
      const out = await runWhatIf(scenario, {
        disruptions: [{ node_id: defaults.node_id, start_d: 0, ...form }],
        mc_runs: 0,
        seed: 42,
      });
      if (out.data) {
        setResult(out.data);
        onResult(out.data);
      } else setError(out.error ?? "The what-if did not run.");
    });

  const field = (key: keyof typeof form, label: string, min: number, max: number, step: number) => (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
        className="tabular rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-sm text-text"
        name={key}
      />
    </label>
  );

  return (
    <section className="flex flex-col gap-3" data-testid="whatif-panel" aria-label="What-if">
      <div>
        <h3 className="text-sm font-semibold tracking-tight">What if {nodeName} is disrupted?</h3>
        <p className="text-xs text-muted">
          Pre-filled from a linked event, else from its recovery-time prior. A daily cascade over inventory, transit and
          qualified alternatives (C1-R02).
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {field("duration_d", "Days", 1, 180, 1)}
        {field("capacity_pct", "Capacity left (%)", 0, 100, 5)}
        {field("extra_lead_time_d", "Extra delay (d)", 0, 60, 1)}
      </div>
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-control)] bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-60"
        data-testid="run-whatif"
      >
        <Play className="size-3.5" aria-hidden />
        {pending ? "Running…" : "Run what-if"}
      </button>
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}
      {result ? (
        <div className="flex flex-col gap-3" data-testid="whatif-result">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            {[
              ["First impact", result.first_impact_d === null || result.first_impact_d === undefined ? "none" : `day ${fmt(result.first_impact_d)}`],
              ["Recovered", result.recovery_d === null || result.recovery_d === undefined ? (result.first_impact_d === null ? "—" : "after horizon") : `day ${fmt(result.recovery_d)}`],
              ["Orders late", fmt(result.orders_late)],
              ["Revenue at risk", usd(result.revenue_at_risk_usd)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-muted">{k}</dt>
                <dd className="tabular text-base font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          {result.tts_d !== null && result.tts_d !== undefined ? (
            <p className="text-xs">
              The network survives <strong>{days(result.tts_d)}</strong> without this node (LP); the disruption lasts{" "}
              <strong>{days(result.duration_d)}</strong>.
            </p>
          ) : null}
          <Timeline result={result} />
          {result.impacted_orders.length ? (
            <table className="w-full text-xs">
              <thead className="text-left text-muted">
                <tr>
                  <th className="py-1 font-medium">Order</th>
                  <th className="py-1 font-medium">Plant</th>
                  <th className="py-1 font-medium">Product</th>
                  <th className="py-1 text-right font-medium">Delay</th>
                  <th className="py-1 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                {result.impacted_orders.slice(0, 6).map((o) => (
                  <tr key={o.order_id} className="border-t border-border">
                    <td className="py-1 font-mono">{o.reference}</td>
                    <td className="max-w-40 truncate py-1" title={o.facility_name}>
                      {o.facility_name}
                    </td>
                    <td className="py-1">{productName(o.product)}</td>
                    <td className={`tabular py-1 text-right ${o.late ? "text-danger" : ""}`}>{days(o.delay_d)}</td>
                    <td className="tabular py-1 text-right">{usd(o.revenue_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-xs text-muted">No open order is delayed: stock and alternatives absorb it.</p>
          )}
          {result.mitigations.length ? (
            <ul className="flex flex-col gap-1.5 text-xs">
              {result.mitigations.map((m) => (
                <li key={m.title} className="rounded-[var(--radius-control)] border border-border p-2">
                  <span className="font-medium">{m.title}</span>
                  <span className="block text-muted">{m.detail}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
