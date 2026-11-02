import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { ShipsBoard } from "@/components/ships-board";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime } from "@/lib/utils";

/** Ships at and around Chattogram at the view time: real GFW names in real data, the simulated
 *  port in a scenario. Status filter and hover details live in the client board. */
export async function ShipsTable({ scenario }: { scenario: string }) {
  const { data, error } = await (await api()).GET("/api/v1/ships", {
    params: { query: { scenario, limit: 80 } },
  });
  if (error || !data) return <ErrorNote what="ships" />;
  const real = !scenario;
  return (
    <Card>
      <CardHeader
        title="Ships at Chattogram"
        subtitle={
          real
            ? `Real port visits (GFW) as observed ${dhakaTime(data.data.observed_at)}; hover a ship for details`
            : "Simulated port (fictional vessels); hover a ship for details"
        }
      />
      <ShipsBoard ships={data.data.ships} counts={data.data.counts} real={real} />
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
