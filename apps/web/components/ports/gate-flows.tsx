import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { fmt } from "@/lib/utils";

type Day = { date: string; in: number; out: number; gates: Record<string, { in: number; out: number }> };

/** Boxes in and out of the port's gates per day: the port end of the trucking corridor (C3). */
function Bars({ days }: { days: Day[] }) {
  const w = 640;
  const h = 180;
  const pad = { l: 40, r: 8, t: 10, b: 24 };
  const hi = Math.max(...days.map((d) => Math.max(d.in, d.out)), 1);
  const step = (w - pad.l - pad.r) / days.length;
  const bw = Math.max(step / 2 - 1, 1);
  const y = (v: number) => h - pad.b - (v / hi) * (h - pad.t - pad.b);
  const ticks = [0, Math.floor(days.length / 2), days.length - 1];
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-[var(--radius-control)] bg-[var(--chart-surface)]" role="img" aria-label="Containers through the port gates per day, in and out">
        {[0, hi / 2, hi].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={pad.l - 4} y={y(v) + 3} textAnchor="end" className="fill-[var(--text-muted)] text-[9px]">{fmt(v)}</text>
          </g>
        ))}
        {days.map((d, i) => {
          const x = pad.l + i * step;
          return (
            <g key={d.date}>
              <title>{`${d.date}: ${fmt(d.in)} in, ${fmt(d.out)} out`}</title>
              <rect x={x} y={y(d.in)} width={bw} height={h - pad.b - y(d.in)} fill="var(--series-1)" />
              <rect x={x + bw + 1} y={y(d.out)} width={bw} height={h - pad.b - y(d.out)} fill="var(--series-2)" />
            </g>
          );
        })}
        {ticks.map((i) => (
          <text key={i} x={pad.l + i * step + step / 2} y={h - 8} textAnchor="middle" className="fill-[var(--text-muted)] text-[9px]">{days[i]?.date.slice(5)}</text>
        ))}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-3 bg-[var(--series-1)]" />in (to the port)</span>
        <span className="flex items-center gap-1"><span className="h-2 w-3 bg-[var(--series-2)]" />out (to the hinterland)</span>
      </figcaption>
    </figure>
  );
}

export async function GateFlows() {
  const { data, error } = await (await api()).GET("/api/v1/ports/{locode}/gates", {
    params: { path: { locode: "BDCGP" }, query: { days: 60, scenario: "" } }, // real data only
  });
  if (error || !data) return <ErrorNote what="gate flows" />;
  const days = (data.data as unknown as Day[]).slice().reverse();
  if (!days.length) return null;
  const full = days.slice(0, -1); // the last day is still counting
  const last = full[full.length - 1] ?? days[days.length - 1];
  const mean = (k: "in" | "out") => full.slice(-30).reduce((a, d) => a + d[k], 0) / Math.max(full.slice(-30).length, 1);
  const busiest = Object.entries(last.gates).sort((a, b) => b[1].in + b[1].out - (a[1].in + a[1].out))[0];
  return (
    <Card data-testid="gate-flows">
      <CardHeader
        title="Containers through the port gates"
        subtitle="Boxes in and out of CPA's gates per day, roughly one truck each: the port end of the road corridor"
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_1fr]">
        <Bars days={days} />
        <dl className="grid grid-cols-2 gap-2 self-start text-xs lg:grid-cols-1">
          <div className="rounded-[var(--radius-control)] border border-border p-2">
            <dt className="text-muted">{last.date}</dt>
            <dd className="tabular text-base font-semibold">{fmt(last.in)} in · {fmt(last.out)} out</dd>
          </div>
          <div className="rounded-[var(--radius-control)] border border-border p-2">
            <dt className="text-muted">Mean per day, last {Math.min(full.length, 30)} full days</dt>
            <dd className="tabular text-base font-semibold">{fmt(mean("in"))} in · {fmt(mean("out"))} out</dd>
          </div>
          {busiest ? (
            <div className="rounded-[var(--radius-control)] border border-border p-2">
              <dt className="text-muted">Busiest gate</dt>
              <dd className="font-semibold">{busiest[0]} <span className="font-normal text-muted">{fmt(busiest[1].in + busiest[1].out)} boxes</span></dd>
            </div>
          ) : null}
        </dl>
      </div>
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
