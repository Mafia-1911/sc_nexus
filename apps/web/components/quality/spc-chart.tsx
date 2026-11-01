"use client";

import type { Spc } from "@/lib/c5";
import { fmt } from "@/lib/utils";

type Point = { produced_at: string; p: number; ucl: number; ewma: number; alarm: boolean; failed: boolean };

/** p-chart per lot (confirmed-defect fraction), its 3σ limit, the EWMA and its limit (C5 §6.3). */
export function SpcChart({ spc }: { spc: Spc }) {
  const pts = spc.points as unknown as Point[];
  const w = 520;
  const h = 200;
  const pad = { l: 40, r: 10, t: 10, b: 24 };
  const hi = Math.max(...pts.map((p) => Math.max(p.p, p.ucl)), spc.ewma_ucl) * 1.1 || 0.01;
  const x = (i: number) => pad.l + (i / Math.max(pts.length - 1, 1)) * (w - pad.l - pad.r);
  const y = (v: number) => h - pad.b - (v / hi) * (h - pad.t - pad.b);
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const pct = (v: number) => `${fmt(v * 100, 1)} %`;
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Defect fraction per lot with control limits and EWMA">
        {[0, hi / 2, hi].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={pad.l - 4} y={y(v) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{pct(v)}</text>
          </g>
        ))}
        <line x1={pad.l} x2={w - pad.r} y1={y(spc.center)} y2={y(spc.center)} stroke="var(--text-muted)" />
        <path d={path(pts.map((p) => p.ucl))} fill="none" stroke="var(--danger)" strokeOpacity={0.6} strokeDasharray="4 3" />
        <line x1={pad.l} x2={w - pad.r} y1={y(spc.ewma_ucl)} y2={y(spc.ewma_ucl)} stroke="var(--warn)" strokeDasharray="6 3" />
        <path d={path(pts.map((p) => p.ewma))} fill="none" stroke="var(--series-1)" strokeWidth={2} />
        <path d={path(pts.map((p) => p.p))} fill="none" stroke="var(--text-muted)" strokeOpacity={0.5} />
        {pts.map((p, i) => (
          <circle key={p.produced_at} cx={x(i)} cy={y(p.p)} r={p.alarm || p.failed ? 4 : 2.5} fill={p.failed ? "var(--danger)" : p.alarm ? "var(--warn)" : "var(--text-muted)"}>
            <title>{`${p.produced_at.slice(0, 10)}: ${pct(p.p)}${p.failed ? " · failed AQL" : ""}${p.alarm ? " · alarm" : ""}`}</title>
          </circle>
        ))}
        <text x={pad.l} y={h - 6} className="fill-[var(--text-muted)] text-[9px]">{pts[0]?.produced_at.slice(0, 10)}</text>
        <text x={w - pad.r} y={h - 6} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{pts[pts.length - 1]?.produced_at.slice(0, 10)}</text>
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--text-muted)]" />centre {pct(spc.center)}</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t-2 border-dashed border-[var(--danger)]" />3σ limit</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--series-1)]" />EWMA</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t-2 border-dashed border-[var(--warn)]" />EWMA limit</span>
        <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[var(--danger)]" />failed AQL</span>
        <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[var(--warn)]" />alarm</span>
      </figcaption>
    </figure>
  );
}
