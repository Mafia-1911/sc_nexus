import { DataBadge } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Card, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { fmt } from "@/lib/utils";

type Point = [string, number];
type Projection = {
  window: [string, string];
  mean_wait_h: number | null;
  p90_wait_h: number | null;
  peak_waiting_for_berth: number;
  vessel_hours_at_port: number;
  queue_daily?: Point[];
};
type Cyclone = { name: string; landfall_h: number; port_closure_h: [number, number]; max_wind_kmh?: number };
type Definition = { cyclone?: Cyclone; supplier_delay?: { lead_time_extra_d: number } };

const H = 3_600_000;
const day = (t: number) => new Date(t).toISOString().slice(0, 10);
const dhaka = (t: number) =>
  new Date(t).toLocaleString("en-GB", { timeZone: "Asia/Dhaka", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Vessels waiting for a berth per day: the scenario's history, then with vs without its shock. */
function QueueChart({ with_, without, start, closure }: { with_: Point[]; without: Point[]; start: string; closure: [number, number] | null }) {
  const w = 640;
  const h = 220;
  const pad = { l: 36, r: 12, t: 12, b: 28 };
  const days = with_.map((p) => p[0]);
  const values = [...with_, ...without].map((p) => p[1]);
  const lo = Math.max(0, Math.floor(Math.min(...values) * 0.9));
  const hi = Math.ceil(Math.max(...values) * 1.05) || 1;
  const x = (i: number) => pad.l + (i / Math.max(days.length - 1, 1)) * (w - pad.l - pad.r);
  const y = (v: number) => h - pad.b - ((v - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
  const n = Math.max(0, days.findIndex((d) => d >= start.slice(0, 10)));
  const line = (pts: [number, number][]) => pts.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const at = (d: string) => days.indexOf(d);
  const shade = closure ? [at(day(closure[0])), at(day(closure[1]))] : null;
  const ticks = [0, Math.floor(n / 2), n, days.length - 1];
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Vessels waiting for a berth per day, with and without the scenario's disruption">
        {shade && shade[0] >= 0 && shade[1] >= 0 ? (
          <rect x={x(shade[0])} width={Math.max(x(shade[1]) - x(shade[0]), 4)} y={pad.t} height={h - pad.t - pad.b} fill="var(--danger)" fillOpacity={0.12} />
        ) : null}
        <line x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} stroke="var(--border-strong)" />
        {[lo, (lo + hi) / 2, hi].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={pad.l - 4} y={y(v) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{fmt(v)}</text>
          </g>
        ))}
        <path d={line(with_.slice(0, n + 1).map((p, i) => [i, p[1]]))} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} />
        <path d={line(without.slice(n).map((p, k) => [n + k, p[1]]))} fill="none" stroke="var(--series-2)" strokeWidth={1.5} strokeDasharray="5 3" />
        <path d={line(with_.slice(n).map((p, k) => [n + k, p[1]]))} fill="none" stroke="var(--series-1)" strokeWidth={2} />
        <line x1={x(n)} x2={x(n)} y1={pad.t} y2={h - pad.b} stroke="var(--border-strong)" />
        <text x={x(n) + 4} y={pad.t + 9} className="fill-[var(--text-muted)] text-[9px]">scenario now</text>
        {ticks.map((i) => (
          <text key={i} x={x(i)} y={h - 10} textAnchor="middle" className="fill-[var(--text-muted)] text-[9px]">{days[i]?.slice(5)}</text>
        ))}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--text-muted)]" />simulated history</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[var(--series-1)]" />with the disruption</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t-2 border-dashed border-[var(--series-2)]" />without it</span>
        {shade ? <span className="flex items-center gap-1"><span className="h-2 w-4 bg-[var(--danger)] opacity-30" />port closed</span> : null}
      </figcaption>
    </figure>
  );
}

/** Scenario mode on Ports & Vessels: the simulated port's congestion, its drivers, with vs
 *  without the shock. Synthetic only (A-111, A-113); C4's model shows with real data. */
export async function ScenarioPort({ scenario }: { scenario: string }) {
  const client = await api();
  const [list, results] = await Promise.all([
    client.GET("/api/v1/scenarios"),
    client.GET("/api/v1/scenarios/{key}/results", { params: { path: { key: scenario } } }),
  ]);
  const row = results.data?.data.find((r) => r.capability === "c4");
  if (!list.data || !row) return <ErrorNote what="the scenario's port projection" />;
  const def = (list.data.data.find((s) => s.key === scenario)?.definition ?? {}) as Definition;
  const k = row.kpis as unknown as { scenario: Projection; without_disruption?: Projection };
  const p = k.scenario;
  const base = k.without_disruption ?? null;
  const start = Date.parse(p.window[0]);
  const cyc = def.cyclone;
  const landfall = cyc ? start + cyc.landfall_h * H : null;
  const closure: [number, number] | null = cyc && landfall ? [landfall + cyc.port_closure_h[0] * H, landfall + cyc.port_closure_h[1] * H] : null;
  const series = p.queue_daily ?? [];
  const tiles: [string, number | null, number | null, string][] = [
    ["Mean berth wait", p.mean_wait_h, base?.mean_wait_h ?? null, "h"],
    ["P90 berth wait", p.p90_wait_h, base?.p90_wait_h ?? null, "h"],
    ["Peak vessels waiting", p.peak_waiting_for_berth, base?.peak_waiting_for_berth ?? null, ""],
    ["Vessel-hours in port", p.vessel_hours_at_port, base?.vessel_hours_at_port ?? null, "h"],
  ];
  const drivers: string[] = [];
  if (cyc && closure && landfall) {
    drivers.push(`Port closed ${dhaka(closure[0])} → ${dhaka(closure[1])} Dhaka (${Math.round((closure[1] - closure[0]) / H)} h) while the cyclone signal is up`);
    drivers.push(`Tropical Cyclone ${cyc.name} (synthetic) makes landfall ${dhaka(landfall)}${cyc.max_wind_kmh ? `, ${cyc.max_wind_kmh} km/h` : ""}`);
    const without = new Map((base?.queue_daily ?? []).map(([d, v]) => [d, v]));
    const gap = series
      .filter(([d]) => d >= p.window[0].slice(0, 10) && without.has(d))
      .map(([d, v]) => [d, v - (without.get(d) ?? v)] as const)
      .reduce<readonly [string, number] | null>((a, g) => (a === null || g[1] > a[1] ? g : a), null);
    if (gap && gap[1] > 0)
      drivers.push(`Largest gap after the closure: +${fmt(gap[1], 1)} vessels waiting on ${gap[0].slice(5)} (simulated)`);
  }
  if (def.supplier_delay) drivers.push(`A supplier's lead time grows by ${def.supplier_delay.lead_time_extra_d} days (inland, not the port)`);
  if (!drivers.length) drivers.push("No disruption: the queue follows normal arrivals, berth capacity and tide windows");
  return (
    <Card data-testid="scenario-port">
      <CardHeader
        title="Simulated congestion · Chattogram"
        subtitle="Vessels waiting for a berth in the scenario's port model, with and without its disruption (14 days ahead)"
        aside={<DataBadge mode="synthetic" sources={["sim", "c4"]} />}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        {series.length ? (
          <QueueChart with_={series} without={base?.queue_daily ?? series} start={p.window[0]} closure={closure} />
        ) : (
          <p className="text-sm text-muted">No daily series in this projection yet: re-seed the scenarios (`make seed-docker`).</p>
        )}
        <div className="flex flex-col gap-3">
          <dl className="grid grid-cols-2 gap-2 text-xs">
            {tiles.map(([label, v, b, unit]) => (
              <div key={label} className="rounded-[var(--radius-control)] border border-border p-2">
                <dt className="text-muted">{label}</dt>
                <dd className="tabular text-base font-semibold">
                  {fmt(v, 1)} {unit}
                </dd>
                {base ? <dd className="text-muted">without: {fmt(b, 1)} {unit}</dd> : null}
              </div>
            ))}
          </dl>
          <div>
            <p className="mb-1 text-xs font-semibold">Drivers</p>
            <ul className="list-disc pl-4 text-xs text-muted" data-testid="drivers">
              {drivers.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Card>
  );
}
