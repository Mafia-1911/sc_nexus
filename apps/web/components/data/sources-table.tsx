import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime, fmt } from "@/lib/utils";

const STATUS_TONE: Record<string, "ok" | "info" | "warn" | "danger" | "neutral"> = {
  verified: "ok",
  manual: "info",
  "needs-registration": "warn",
  blocked: "danger",
};

/** Source registry (05 §4 Data & Models): mode, two-strikes state, freshness, rows, licence. */
export async function SourcesTable() {
  const { data, error } = await (await api()).GET("/api/v1/sources");
  if (error || !data) return <ErrorNote what="sources" />;
  const rows = data.data.filter((s) => s.tier !== "P2");
  return (
    <Card>
      <CardHeader
        title="Data sources"
        subtitle="Every source the platform reads, the mode it runs in, and whether it can be trusted right now"
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="sources">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-medium">Source</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Mode</th>
              <th className="py-2 pr-3 font-medium">Last success</th>
              <th className="py-2 pr-3 text-right font-medium">Rows</th>
              <th className="py-2 pr-3 font-medium">Licence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((s) => {
              const mode = s.effective_mode ?? s.default_mode ?? "off";
              const degraded = s.failures >= 2;
              return (
                <tr key={s.ds_id} data-source={s.ds_id}>
                  <td className="py-2 pr-3">
                    <div className="font-mono text-xs text-muted">{s.ds_id} · {s.tier}</div>
                    <div className="max-w-xs truncate" title={s.name}>{s.name}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                  </td>
                  <td className="py-2 pr-3 text-xs">
                    <span className={degraded ? "text-warn" : undefined}>
                      {mode}
                      {degraded ? ` (fallback after ${s.failures} failures)` : ""}
                    </span>
                    {s.cadence ? <div className="text-muted">{s.cadence}</div> : null}
                  </td>
                  <td className="tabular py-2 pr-3 text-xs">
                    {s.last_success_ts ? dhakaTime(s.last_success_ts) : "—"}
                    {s.freshness_h !== null && s.freshness_h !== undefined ? (
                      <div className="text-muted">{fmt(s.freshness_h, 1)} h ago</div>
                    ) : null}
                  </td>
                  <td className="tabular py-2 pr-3 text-right text-xs">{fmt(s.records_last_run ?? null)}</td>
                  <td className="py-2 pr-3 text-xs">
                    <div className="flex items-start gap-2">
                      {s.nc ? <Badge tone="warn" title="Non-commercial licence (Q-06)">NC</Badge> : null}
                      <span className="line-clamp-2 max-w-sm text-muted" title={s.licence ?? undefined}>
                        {s.licence ?? "—"}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
