import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime } from "@/lib/utils";

/** Shipments in flight; P50/P90 ETAs fill in when C4 and Nexus land (M6, M8). */
export async function ShipmentsTable({ scenario }: { scenario: string }) {
  const { data, error } = await (await api()).GET("/api/v1/shipments", {
    params: { query: { scenario, limit: 12, active: true } },
  });
  if (error || !data) return <ErrorNote what="shipments" />;
  return (
    <Card>
      <CardHeader title="Shipments" subtitle="Planned arrivals; forecast ETAs arrive with C4 (M6)" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="shipments">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-medium">Reference</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Modes</th>
              <th className="py-2 pr-3 font-medium">Planned ETA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.data.map((s) => (
              <tr key={s.id}>
                <td className="py-2 pr-3 font-mono text-xs">{s.reference}</td>
                <td className="py-2 pr-3">
                  <Badge tone={s.status === "delayed" ? "danger" : s.status === "in_transit" ? "info" : "neutral"}>
                    {s.status.replace("_", " ")}
                  </Badge>
                </td>
                <td className="py-2 pr-3 text-xs text-muted">{s.mode_chain.join(" → ")}</td>
                <td className="tabular py-2 pr-3 text-xs">{dhakaTime(s.planned_eta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
