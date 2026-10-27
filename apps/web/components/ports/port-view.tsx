"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useMemo, useState, useTransition } from "react";

import { loadSnapshot, loadTrack } from "@/app/ports/actions";
import { DataBadge } from "@/components/data-badge";
import { FanChart } from "@/components/ports/fan-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { type Snapshot, type VesselInPort, type VesselTrack, CARGO, inBand, span } from "@/lib/c4";
import { cn, dhakaTime, fmt } from "@/lib/utils";

type Metrics = Record<string, Record<string, unknown>>;

function num(m: Metrics, model: string, ...path: string[]): number | null {
  let v: unknown = m[model];
  for (const k of path) v = (v as Record<string, unknown> | undefined)?.[k];
  return typeof v === "number" ? v : null;
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-border bg-surface/85 p-4 shadow-sm backdrop-blur-md">
      <span className="text-xs text-muted">{label}</span>
      <span className="tabular text-2xl font-semibold">{value}</span>
      {detail ? <span className="text-xs text-muted">{detail}</span> : null}
    </div>
  );
}

/** Departure window on a shared axis: P10–P90 bar, P50 tick, actual departure dot (replay). */
function Window({ v, asOf, maxH }: { v: VesselInPort; asOf: number; maxH: number }) {
  const pos = (iso: string) => Math.min(100, Math.max(0, ((Date.parse(iso) - asOf) / 3.6e6 / maxH) * 100));
  const hit = inBand(v);
  return (
    <div className="relative h-3 w-40 rounded-full bg-surface-2" aria-hidden>
      <span className="absolute top-0 h-3 rounded-full bg-[var(--series-1)] opacity-35" style={{ left: `${pos(v.departure_p10)}%`, width: `${Math.max(pos(v.departure_p90) - pos(v.departure_p10), 1)}%` }} />
      <span className="absolute top-0 h-3 w-0.5 bg-[var(--series-1)]" style={{ left: `${pos(v.departure_p50)}%` }} />
      {v.actual_departure_ts ? (
        <span className={cn("absolute top-0.5 size-2 rounded-full", hit ? "bg-[var(--ok)]" : "bg-[var(--danger)]")} style={{ left: `calc(${pos(v.actual_departure_ts)}% - 4px)` }} />
      ) : null}
    </div>
  );
}

function TrackChart({ track }: { track: VesselTrack }) {
  const w = 360;
  const h = 150;
  const pad = { l: 8, r: 8, t: 10, b: 22 };
  const u = track.updates as { as_of: string; departure_p10: string; departure_p50: string; departure_p90: string }[];
  const actual = track.vessel.actual_departure_ts ? Date.parse(track.vessel.actual_departure_ts) : null;
  const ts = u.flatMap((r) => [Date.parse(r.departure_p10), Date.parse(r.departure_p90)]).concat(actual ? [actual] : []);
  const lo = Math.min(...ts);
  const hi = Math.max(...ts);
  const x = (i: number) => pad.l + (i / Math.max(u.length - 1, 1)) * (w - pad.l - pad.r);
  const y = (t: number) => pad.t + ((t - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Expected departure at each daily snapshot">
        {u.map((r, i) => (
          <g key={r.as_of}>
            <line x1={x(i)} x2={x(i)} y1={y(Date.parse(r.departure_p10))} y2={y(Date.parse(r.departure_p90))} stroke="var(--series-1)" strokeOpacity={0.45} strokeWidth={6} strokeLinecap="round" />
            <circle cx={x(i)} cy={y(Date.parse(r.departure_p50))} r={3} fill="var(--series-1)" />
          </g>
        ))}
        {actual ? <line x1={pad.l} x2={w - pad.r} y1={y(actual)} y2={y(actual)} stroke="var(--text)" strokeDasharray="4 3" /> : null}
        <text x={pad.l} y={h - 6} className="fill-[var(--text-muted)] text-[9px]">{dhakaTime(u[0]?.as_of)}</text>
        <text x={w - pad.r} y={h - 6} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{dhakaTime(u[u.length - 1]?.as_of)}</text>
      </svg>
      <figcaption className="mt-1 text-[11px] text-muted">Each column is one daily snapshot: the departure window (P10–P90) and P50. Later is lower. Dashed: actual departure.</figcaption>
    </figure>
  );
}

function Drawer({ v, track, onClose }: { v: VesselInPort; track: VesselTrack | null; onClose: () => void }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col gap-4 overflow-y-auto border-l border-border bg-surface p-5 shadow-xl" data-testid="vessel-drawer" aria-label={`Vessel ${v.name ?? v.mmsi}`}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{v.name ?? `MMSI ${v.mmsi}`}</h2>
          <p className="text-xs text-muted">{(v.ship_type ?? "unknown type").replace("_", " ")} · flag {v.flag ?? "—"} · MMSI {v.mmsi}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface-2"><X className="size-4" /></button>
      </header>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div><dt className="text-xs text-muted">Arrived</dt><dd>{dhakaTime(v.arrival_ts)}</dd></div>
        <div><dt className="text-xs text-muted">In port at snapshot</dt><dd className="tabular">{span(v.elapsed_h)}</dd></div>
        <div><dt className="text-xs text-muted">Leaves (P50)</dt><dd>{dhakaTime(v.departure_p50)}</dd></div>
        <div><dt className="text-xs text-muted">80 % window</dt><dd className="text-xs">{dhakaTime(v.departure_p10)} → {dhakaTime(v.departure_p90)}</dd></div>
        <div><dt className="text-xs text-muted">Stay at arrival, model (P50)</dt><dd className="tabular">{span(v.dwell_at_arrival?.p50)} <span className="text-xs text-muted">({span(v.dwell_at_arrival?.p10)}–{span(v.dwell_at_arrival?.p90)})</span></dd></div>
        <div><dt className="text-xs text-muted">Baseline median</dt><dd className="tabular">{span(v.baseline_at_arrival?.p50)}</dd></div>
        {v.actual_departure_ts ? (
          <div className="col-span-2"><dt className="text-xs text-muted">What happened (replay)</dt><dd>left {dhakaTime(v.actual_departure_ts)} after {span(v.actual_dwell_h)} {inBand(v) ? <Badge tone="ok">inside the window</Badge> : <Badge tone="danger">outside the window</Badge>}</dd></div>
        ) : null}
      </dl>
      <section>
        <h3 className="mb-2 text-sm font-semibold">Why this estimate</h3>
        <ul className="flex flex-col gap-1.5 text-sm" data-testid="drivers">
          {(v.drivers as { label: string; value: string; effect_pct: number }[]).map((d) => (
            <li key={d.label} className="flex items-center justify-between gap-2">
              <span>{d.label}: <span className="tabular font-medium">{d.value}</span></span>
              <span className={cn("tabular text-xs", d.effect_pct > 0 ? "text-warn" : "text-ok")}>{d.effect_pct > 0 ? "+" : ""}{fmt(d.effect_pct)} % stay</span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-[11px] text-muted">TreeSHAP contributions of the P50 model at arrival.</p>
      </section>
      <section>
        <h3 className="mb-2 text-sm font-semibold">How the estimate moved</h3>
        {track ? <TrackChart track={track} /> : <div className="skeleton h-36 w-full" />}
      </section>
    </aside>
  );
}

export function PortView({ locode, initial, actual }: { locode: string; initial: Snapshot; actual: [string, number][] }) {
  const [snap, setSnap] = useState(initial);
  const [cargoOnly, setCargoOnly] = useState(true);
  const [open, setOpen] = useState<VesselInPort | null>(null);
  const [track, setTrack] = useState<VesselTrack | null>(null);
  const [pending, start] = useTransition();
  const times = snap.forecast.snapshots;
  const idx = times.indexOf(snap.forecast.as_of);
  const asOf = Date.parse(snap.forecast.as_of);
  const actualMap = useMemo(() => new Map(actual), [actual]);
  const metrics = snap.forecast.metrics as Metrics;
  const rows = snap.vessels.filter((v) => !cargoOnly || CARGO.has(v.ship_type ?? ""));
  const maxH = Math.max(72, ...rows.map((v) => (Date.parse(v.departure_p90) - asOf) / 3.6e6));
  const scored = rows.filter((v) => inBand(v) !== null);
  const hits = scored.filter((v) => inBand(v)).length;
  const last = snap.forecast.history[snap.forecast.history.length - 1];
  const week = snap.forecast.forecast[6];

  const go = (i: number) => {
    const t = times[Math.max(0, Math.min(times.length - 1, i))];
    start(async () => {
      const out = await loadSnapshot(locode, t);
      if (out.data) setSnap(out.data);
      setOpen(null);
    });
  };
  const pick = (v: VesselInPort) => {
    setOpen(v);
    setTrack(null);
    void loadTrack(v.vessel_id, snap.forecast.as_of).then(setTrack);
  };

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Snapshot</span>
        <button type="button" onClick={() => go(idx - 1)} disabled={pending || idx <= 0} aria-label="Previous day" className="rounded border border-border p-1 disabled:opacity-40"><ChevronLeft className="size-4" /></button>
        <input type="range" min={0} max={times.length - 1} value={idx} onChange={(e) => go(Number(e.target.value))} aria-label="Snapshot day" className="w-56 accent-[var(--primary)]" />
        <button type="button" onClick={() => go(idx + 1)} disabled={pending || idx >= times.length - 1} aria-label="Next day" className="rounded border border-border p-1 disabled:opacity-40"><ChevronRight className="size-4" /></button>
        <span className="tabular text-sm" data-testid="snapshot">{dhakaTime(snap.forecast.as_of)}</span>
        {pending ? <span className="text-xs text-muted">loading…</span> : null}
        <span className="ml-auto"><DataBadge mode={snap.meta.mode} sources={snap.meta.sources} asOf={snap.meta.as_of} modes={snap.meta.modes} /></span>
        <p className="w-full text-xs text-muted">{snap.meta.note}</p>
      </Card>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="port-kpis">
        <Tile label="Vessels in port" value={fmt(snap.vessels.length)} detail={`${fmt(snap.vessels.filter((v) => CARGO.has(v.ship_type ?? "")).length)} cargo`} />
        <Tile label="Outer anchorage" value={last ? fmt(last[1]) : "—"} detail={week ? `in 7 days: ${fmt(week[2])} (${fmt(week[1])}–${fmt(week[3])})` : undefined} />
        <Tile label="Departure windows that held" value={scored.length ? `${fmt((hits / scored.length) * 100)} %` : "—"} detail={`${hits} of ${scored.length} shown vessels left inside P10–P90 (target 80 %)`} />
        <Tile label="Model vs median baseline" value={num(metrics, "c4-dwell-lgbm-cqr", "mae_gain_cargo") !== null ? `−${fmt((num(metrics, "c4-dwell-lgbm-cqr", "mae_gain_cargo") ?? 0) * 100)} % error` : "—"} detail={`cargo dwell MAE on the test window; 80 % band covers ${fmt((num(metrics, "c4-dwell-lgbm-cqr", "L1_cargo", "coverage_80") ?? 0) * 100)} %`} />
      </div>
      <Card data-testid="queue-fan">
        <CardHeader title="Outer anchorage queue" subtitle="Vessels per day (GFW presence) and the 14-day forecast with its 80 % band" />
        <FanChart history={snap.forecast.history as [string, number][]} forecast={snap.forecast.forecast as [string, number, number, number][]} actual={actualMap} />
      </Card>
      <Card>
        <CardHeader
          title="Vessels in port"
          subtitle="Soonest expected departure first; bar = 80 % window, tick = P50, dot = actual (green inside, red outside)"
          aside={
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={cargoOnly} onChange={(e) => setCargoOnly(e.target.checked)} /> cargo and tankers only
            </label>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="vessel-table">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Vessel</th>
                <th className="py-1.5 pr-3 font-medium">Arrived</th>
                <th className="py-1.5 pr-3 font-medium">In port</th>
                <th className="py-1.5 pr-3 font-medium">Leaves (P50)</th>
                <th className="py-1.5 pr-3 font-medium">Window, next {span(maxH)}</th>
                <th className="py-1.5 pr-3 font-medium">Main driver</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 60).map((v) => {
                const top = (v.drivers as { label: string; value: string; effect_pct: number }[])[0];
                return (
                  <tr key={v.call_id} onClick={() => pick(v)} className="cursor-pointer border-t border-border hover:bg-surface-2" data-call={v.call_id}>
                    <td className="py-1.5 pr-3"><span className="font-medium">{v.name ?? `MMSI ${v.mmsi}`}</span> <span className="text-xs text-muted">{v.flag ?? ""}</span></td>
                    <td className="py-1.5 pr-3 text-xs">{dhakaTime(v.arrival_ts)}</td>
                    <td className="tabular py-1.5 pr-3">{span(v.elapsed_h)}</td>
                    <td className="py-1.5 pr-3 text-xs">{dhakaTime(v.departure_p50)}</td>
                    <td className="py-1.5 pr-3"><Window v={v} asOf={asOf} maxH={maxH} /></td>
                    <td className="py-1.5 pr-3 text-xs text-muted">{top ? `${top.label} ${top.effect_pct > 0 ? "+" : ""}${fmt(top.effect_pct)} %` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length > 60 ? <p className="mt-2 text-xs text-muted">Showing 60 of {rows.length}.</p> : null}
        </div>
      </Card>
      {open ? <Drawer v={open} track={track} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
