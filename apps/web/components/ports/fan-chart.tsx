"use client";

import { fmt } from "@/lib/utils";

type Point = [string, number];
type Fan = [string, number, number, number];

/** Anchorage queue: 60 days of history, the P10–P90 fan and P50 ahead; in replay, what happened. */
export function FanChart({ history, forecast, actual }: { history: Point[]; forecast: Fan[]; actual: Map<string, number> }) {
  const w = 640;
  const h = 220;
  const pad = { l: 36, r: 12, t: 12, b: 28 };
  const days = [...history.map((p) => p[0]), ...forecast.map((f) => f[0])];
  const ahead = forecast.map((f) => actual.get(f[0])).filter((v): v is number => v !== undefined);
  const values = [...history.map((p) => p[1]), ...forecast.flatMap((f) => [f[1], f[3]]), ...ahead];
  const lo = Math.floor(Math.min(...values) * 0.9);
  const hi = Math.ceil(Math.max(...values) * 1.05);
  const x = (i: number) => pad.l + (i / Math.max(days.length - 1, 1)) * (w - pad.l - pad.r);
  const y = (v: number) => h - pad.b - ((v - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
  const n = history.length;
  const line = (pts: [number, number][]) => pts.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const band =
    line(forecast.map((f, k) => [n + k, f[3]])) +
    " " +
    forecast
      .map((f, k) => [n + k, f[1]] as [number, number])
      .reverse()
      .map(([i, v]) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`)
      .join(" ") +
    " Z";
  const happened = forecast.map((f, k) => [n + k, actual.get(f[0])] as [number, number | undefined]).filter((p): p is [number, number] => p[1] !== undefined);
  const ticks = [0, Math.floor(n / 2), n - 1, days.length - 1];
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Vessels in the outer anchorage per day: history, forecast median and 80 % band">
        <line x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} stroke="var(--border-strong)" />
        {[lo, (lo + hi) / 2, hi].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={pad.l - 4} y={y(v) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{fmt(v)}</text>
          </g>
        ))}
        <path d={band} fill="var(--series-1)" fillOpacity={0.18} />
        <path d={line(history.map((p, i) => [i, p[1]]))} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} />
        <path d={line([[n - 1, history[n - 1]?.[1] ?? 0], ...forecast.map((f, k) => [n + k, f[2]] as [number, number])])} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeDasharray="5 3" />
        {happened.length ? <path d={line(happened)} fill="none" stroke="var(--text)" strokeWidth={1.5} /> : null}
        <line x1={x(n - 1)} x2={x(n - 1)} y1={pad.t} y2={h - pad.b} stroke="var(--border-strong)" />
        <text x={x(n - 1) + 4} y={pad.t + 9} className="fill-[var(--text-muted)] text-[9px]">snapshot</text>
        {ticks.map((i) => (
          <text key={i} x={x(i)} y={h - 10} textAnchor="middle" className="fill-[var(--text-muted)] text-[9px]">{days[i]?.slice(5)}</text>
        ))}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--text-muted)]" />history</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t-2 border-dashed border-[var(--series-1)]" />forecast P50</span>
        <span className="flex items-center gap-1"><span className="h-2 w-4 bg-[var(--series-1)] opacity-30" />P10–P90</span>
        {happened.length ? <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--text)]" />what happened (replay)</span> : null}
      </figcaption>
    </figure>
  );
}
