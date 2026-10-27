"use client";

import type { Plan } from "@/lib/c3";
import { taka } from "@/lib/c3";

/** Time (P50, with a P90 whisker) vs cost; colour depth = CO2e; ring = selected (05 §7). */
export function ParetoChart({ plans, selected, onSelect }: { plans: Plan[]; selected: number; onSelect: (i: number) => void }) {
  const w = 420;
  const h = 220;
  const pad = { l: 56, r: 12, t: 12, b: 34 };
  const maxT = Math.max(...plans.map((p) => p.time_p90_h)) * 1.08;
  const costs = plans.map((p) => p.cost_bdt);
  const minC = Math.min(...costs) * 0.9;
  const maxC = Math.max(...costs) * 1.08;
  const co2 = plans.map((p) => p.co2e_kg);
  const lo = Math.min(...co2);
  const hi = Math.max(...co2);
  const x = (t: number) => pad.l + (t / maxT) * (w - pad.l - pad.r);
  const y = (c: number) => h - pad.b - ((c - minC) / (maxC - minC || 1)) * (h - pad.t - pad.b);
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Plans by hours (P50, whisker to P90) and cost; darker is more CO2e">
        <line x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} stroke="var(--border-strong)" />
        <line x1={pad.l} x2={pad.l} y1={pad.t} y2={h - pad.b} stroke="var(--border-strong)" />
        <text x={(w + pad.l) / 2} y={h - 6} textAnchor="middle" className="fill-[var(--text-muted)] text-[10px]">hours to arrive (P50 → P90)</text>
        <text x={12} y={(h - pad.b) / 2} transform={`rotate(-90 12 ${(h - pad.b) / 2})`} textAnchor="middle" className="fill-[var(--text-muted)] text-[10px]">cost</text>
        <text x={pad.l - 4} y={y(minC / 0.9) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{taka(minC / 0.9)}</text>
        <text x={pad.l - 4} y={y(maxC / 1.08) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{taka(maxC / 1.08)}</text>
        {plans.map((p, i) => {
          const depth = hi > lo ? (p.co2e_kg - lo) / (hi - lo) : 0.5;
          return (
            <g key={p.name} onClick={() => onSelect(i)} className="cursor-pointer" data-plan={i}>
              <line x1={x(p.time_p50_h)} x2={x(p.time_p90_h)} y1={y(p.cost_bdt)} y2={y(p.cost_bdt)} stroke="var(--primary)" strokeOpacity={0.5} strokeWidth={2} />
              <circle cx={x(p.time_p50_h)} cy={y(p.cost_bdt)} r={i === selected ? 8 : 6} fill="var(--primary)" fillOpacity={0.25 + 0.75 * depth} stroke={i === selected ? "var(--text)" : "var(--surface)"} strokeWidth={i === selected ? 2 : 1} />
              <text x={x(p.time_p50_h) + 9} y={y(p.cost_bdt) - 8} className="fill-[var(--text)] text-[10px]">{p.name}{p.pareto_rank ? " (dominated)" : ""}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 text-[11px] text-muted">Darker dots emit more CO2e. Dominated plans are shown for comparison.</figcaption>
    </figure>
  );
}
