"use client";

import { Route } from "lucide-react";
import { useMemo, useState, useTransition } from "react";

import { optimize } from "@/app/routes/actions";
import { ParetoChart } from "@/components/routes/pareto-chart";
import { RouteMap } from "@/components/routes/route-map";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { type Place, type Plan, type RouteResult, MODE_VAR, taka } from "@/lib/c3";
import { cn, dhakaTime, fmt } from "@/lib/utils";

function localInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function ModeMix({ plan }: { plan: Plan }) {
  const total = plan.legs.reduce((s, l) => s + l.km, 0) || 1;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-2" aria-label="Distance by mode">
      {plan.legs
        .filter((l) => l.km > 0)
        .map((l, i) => (
          <span key={i} style={{ width: `${(l.km / total) * 100}%`, background: `var(${MODE_VAR[l.mode] ?? "--border-strong"})` }} title={`${l.mode} ${fmt(l.km)} km`} />
        ))}
    </div>
  );
}

function OnTime({ p }: { p: number | null | undefined }) {
  if (p === null || p === undefined) return <span className="text-muted">no deadline</span>;
  const tone = p >= 0.8 ? "ok" : p >= 0.5 ? "warn" : "danger";
  return <Badge tone={tone}>{fmt(p * 100)}% on time</Badge>;
}

export function Planner({ places }: { places: Place[] }) {
  const now = useMemo(() => new Date(), []);
  const [form, setForm] = useState({
    origin: "BDCGP",
    dest: "gazipur",
    qty_teu: 2,
    reefer: false,
    deadline: localInput(new Date(now.getTime() + 36 * 3600 * 1000)),
  });
  const [result, setResult] = useState<RouteResult | null>(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const run = () =>
    start(async () => {
      setError(null);
      const out = await optimize({
        origin: form.origin,
        dest: form.dest,
        qty_teu: form.qty_teu,
        cargo_profile: form.reefer ? "REEFER_2_8C" : "DRY_CONTAINER",
        deadline: new Date(form.deadline).toISOString(),
      });
      if (out.data) {
        setResult(out.data);
        setSelected(0);
      } else setError(out.error ?? "Planning failed.");
    });

  const plan = result?.plans[selected] ?? null;
  const select = (label: string, key: "origin" | "dest") => (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <select
        name={key}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className="rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-sm text-text"
      >
        {places.map((p) => (
          <option key={p.key} value={p.key}>
            {p.name}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="grid grid-cols-2 items-end gap-3 md:grid-cols-6">
          {select("From", "origin")}
          {select("To", "dest")}
          <label className="flex flex-col gap-1 text-xs text-muted">
            Deliver by
            <input type="datetime-local" name="deadline" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} className="rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-sm text-text" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            TEU
            <input type="number" min={1} max={200} name="qty_teu" value={form.qty_teu} onChange={(e) => setForm({ ...form, qty_teu: Number(e.target.value) })} className="tabular rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-sm text-text" />
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={form.reefer} onChange={(e) => setForm({ ...form, reefer: e.target.checked })} />
            Cold chain (reefer)
          </label>
          <button type="button" onClick={run} disabled={pending} className="inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-primary px-3 py-2 text-sm font-medium text-on-primary disabled:opacity-60" data-testid="plan-route">
            <Route className="size-4" aria-hidden />
            {pending ? "Planning…" : "Plan routes"}
          </button>
        </div>
        {error ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
      </Card>
      {result && plan ? (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
            <Card className="xl:col-span-2" data-testid="pareto">
              <CardHeader title="Trade-offs" subtitle="Fast, cheap or green: the non-dominated plans first" />
              <ParetoChart plans={result.plans} selected={selected} onSelect={setSelected} />
            </Card>
            <Card className="xl:col-span-3">
              <CardHeader title="The route" subtitle={plan.name} aside={<ul className="flex gap-3 text-xs text-muted">{Object.entries(MODE_VAR).map(([m, v]) => (<li key={m} className="flex items-center gap-1"><span className="size-2.5 rounded-full" style={{ background: `var(${v})` }} />{m}</li>))}</ul>} />
              <div className="relative h-[300px] overflow-hidden rounded-[var(--radius-control)] border border-border">
                <RouteMap plan={plan} />
              </div>
            </Card>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="plan-cards">
            {result.plans.map((p, i) => (
              <button key={p.name} type="button" onClick={() => setSelected(i)} className={cn("flex flex-col gap-2 rounded-[var(--radius-card)] border bg-surface/85 p-3 text-left backdrop-blur-md", i === selected ? "border-primary" : "border-border")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold">{p.name}</span>
                  {p.pareto_rank === 0 ? <Badge tone="info">best trade-off</Badge> : <Badge>dominated</Badge>}
                </div>
                <ModeMix plan={p} />
                <dl className="grid grid-cols-3 gap-1 text-xs">
                  <div><dt className="text-muted">P50 / P90</dt><dd className="tabular font-semibold">{fmt(p.time_p50_h, 1)} / {fmt(p.time_p90_h, 1)} h</dd></div>
                  <div><dt className="text-muted">Cost</dt><dd className="tabular font-semibold">{taka(p.cost_bdt)}</dd></div>
                  <div><dt className="text-muted">CO2e</dt><dd className="tabular font-semibold">{fmt(p.co2e_kg)} kg</dd></div>
                </dl>
                <div className="flex items-center justify-between text-xs text-muted">
                  <span>arrive {dhakaTime(p.arrival_p50)}</span>
                  <OnTime p={p.on_time_prob} />
                </div>
                <p className="text-xs text-muted">{p.explanation}</p>
              </button>
            ))}
          </div>
          {plan.departures.length ? (
            <Card>
              <CardHeader title="When to leave" subtitle={`${plan.name}: chance of arriving by the deadline, by departure time`} />
              <div className="flex gap-1 overflow-x-auto" data-testid="departures">
                {plan.departures.map((d) => {
                  const p = Number(d.on_time_prob ?? 0);
                  return (
                    <div key={String(d.depart)} className="flex min-w-16 flex-col items-center gap-1 text-[11px]" title={`P90 ${d.p90_h} h`}>
                      <span className="h-8 w-full rounded" style={{ background: "var(--ok)", opacity: 0.15 + 0.85 * p }} />
                      <span className="tabular">{fmt(p * 100)}%</span>
                      <span className="text-muted">{dhakaTime(String(d.depart)).replace(" BST", "")}</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : null}
          <ul className="text-xs text-muted">
            {result.notes.map((n) => (
              <li key={n}>• {n}</li>
            ))}
            {plan.legs
              .filter((l) => l.factor)
              .map((l, i) => (
                <li key={`f${i}`}>• {l.mode} CO2e: {String(l.factor?.label)} ({String(l.factor?.source)} {String(l.factor?.year)}), {String(l.factor?.value)} kg/t·km</li>
              ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
