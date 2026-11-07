import { DataBadge } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { PortLiveMap } from "@/components/port-live-map";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime, fmt } from "@/lib/utils";

type Yard = { yard: string; capacity_teu: number | null; used_teu: number | null; used_pct: number | null };
type Ship = { name: string; eta: string | null; agent: string | null };

/** Chattogram now from CPA's public TOS dashboard and PCS (DS-PORT-10), polled by the worker. */
export async function PortLive() {
  const { data, error } = await (await api()).GET("/api/v1/port/live");
  if (error || !data) return <ErrorNote what="CPA port data" />;
  const d = data.data as Record<string, unknown>;
  if (!d.available) return <ErrorNote what="CPA port data (the worker polls cpatos.gov.bd every 15 minutes)" />;
  const counts = (d.counts ?? {}) as Record<string, number>;
  const yards = ((d.yards ?? []) as Yard[]).filter((y) => y.yard !== "Grand Total");
  const total = ((d.yards ?? []) as Yard[]).find((y) => y.yard === "Grand Total");
  const expected = (d.expected ?? []) as Ship[];
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3" data-testid="port-live">
      <Card className="xl:col-span-2">
        <CardHeader
          title="Chattogram port now"
          subtitle={`CPA TOS + PCS: ${counts.at_berth ?? 0} at berth, ${counts.at_anchorage ?? 0} at the outer anchorage, ${counts.expected ?? 0} expected · berth positions approximate, anchorage spots illustrative`}
        />
        <PortLiveMap vessels={d.vessels as GeoJSON.FeatureCollection} berths={d.berths as GeoJSON.FeatureCollection} />
        <CardFooter>
          <DataBadge mode="live" sources={["DS-PORT-10"]} asOf={d.observed_at as string} />
          <span className="text-xs text-muted">as of {dhakaTime(d.observed_at as string)}{d.fresh ? "" : " (stale: the last poll is over 2 h old)"}</span>
        </CardFooter>
      </Card>
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="Yard occupancy" subtitle={total ? `All yards ${fmt(total.used_pct ?? 0, 0)}% of capacity` : "per terminal yard"} />
          <ul className="flex flex-col gap-2" data-testid="yards">
            {yards.map((y) => {
              const pct = y.used_pct ?? 0;
              return (
                <li key={y.yard} className="text-xs">
                  <div className="flex justify-between">
                    <span className="font-medium">{y.yard}</span>
                    <span className="tabular">
                      {fmt(y.used_teu ?? 0)} / {fmt(y.capacity_teu ?? 0)} TEU · <strong className={pct > 100 ? "text-danger" : pct > 85 ? "text-warn" : ""}>{fmt(pct, 0)}%</strong>
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-2" aria-hidden>
                    <div className={`h-1.5 rounded-full ${pct > 100 ? "bg-danger" : pct > 85 ? "bg-warn" : "bg-ok"}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Expected next" subtitle="PCS inbound vessels by ETA (agents' declarations)" />
          <ul className="flex flex-col divide-y divide-border text-xs" data-testid="expected">
            {expected.slice(0, 8).map((s) => (
              <li key={`${s.name}-${s.eta}`} className="flex justify-between py-1.5">
                <span className="truncate font-medium" title={s.name}>{s.name}</span>
                <span className="tabular text-muted">{dhakaTime(s.eta)} · {s.agent ?? "—"}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
