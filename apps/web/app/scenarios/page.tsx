import { Suspense } from "react";

import { DataBadge } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { PrintButton } from "@/components/scenarios/print-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import { usd } from "@/lib/c5";
import { currentScenario } from "@/lib/scenario";
import { fmt } from "@/lib/utils";

export const generateMetadata = () => titled("Scenario Studio");

type Policy = {
  orders_at_risk: { production: number; quality: number; in_transit: number; total: number };
  revenue_at_risk_usd: number;
  otif: number | null;
  action_cost_usd: number;
  co2e_inland_kg_per_teu: number | null;
  co2e_actions_kg: number;
};
type Delta = {
  orders_saved: number;
  otif_pts: number | null;
  lateness_cost_avoided_usd: number;
  of_which_quality_usd: number;
  action_cost_usd: number;
  net_usd: number;
  co2e_kg: number;
};
type Action = {
  id: string;
  type: string;
  source: string;
  cost_usd: number | null;
  benefit_usd: number | null;
  confidence: number | null;
  rationale: string | null;
};
type Kpis = {
  policies: { baseline: Policy; nexus_recommended: Policy };
  at_p50: Record<string, { production_late: number; revenue_at_risk_usd: number }>;
  delta: Delta;
  as_of: string;
};

const ACTION: Record<string, string> = {
  increase_safety_stock: "Raise safety stock",
  pull_forward_po: "Pull the PO forward",
  reroute: "Export via Mongla",
  rework: "Rework the lot",
  replace_production: "Replace production",
  expedite_air: "Air freight",
  notify_customer: "Notify the buyer",
};

/** Unknown is a dash, never zero (no DESNZ factors ingested → no K-07). */
function kg(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${fmt(v, 1)} kg`;
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${fmt(v * 100, 1)}%`;
}

function Tile({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`tabular text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
      {note ? <p className="text-[11px] text-muted">{note}</p> : null}
    </div>
  );
}

async function Studio() {
  const scenario = await currentScenario();
  const client = await api();
  const { data, error } = await client.GET("/api/v1/scenarios/{key}/results", {
    params: { path: { key: scenario } },
  });
  if (error || !data) return <ErrorNote what="scenario results" />;
  const row = data.data.find((r) => r.capability === "nexus");
  if (!row) {
    return <ErrorNote what="the Nexus comparison (the worker computes it a minute after start)" />;
  }
  const k = row.kpis as unknown as Kpis;
  const actions = (row.artifacts.actions ?? []) as Action[];
  const alerts = (row.artifacts.alerts ?? []) as { title: string }[];
  const { baseline: b, nexus_recommended: n } = k.policies;
  const d = k.delta;
  const rows: [string, string, string, string][] = [
    ["Orders at risk, production (P90)", fmt(b.orders_at_risk.production, 1), fmt(n.orders_at_risk.production, 1), fmt(n.orders_at_risk.production - b.orders_at_risk.production, 1)],
    ["Orders at risk, quality", fmt(b.orders_at_risk.quality), fmt(n.orders_at_risk.quality), fmt(n.orders_at_risk.quality - b.orders_at_risk.quality)],
    ["Orders at risk, in transit (door P90 > due)", fmt(b.orders_at_risk.in_transit), fmt(n.orders_at_risk.in_transit), fmt(n.orders_at_risk.in_transit - b.orders_at_risk.in_transit)],
    ["Revenue at risk, production (P90)", usd(b.revenue_at_risk_usd), usd(n.revenue_at_risk_usd), usd(n.revenue_at_risk_usd - b.revenue_at_risk_usd)],
    ["OTIF, production and quality (K-06)", pct(b.otif), pct(n.otif), d.otif_pts === null ? "—" : `${d.otif_pts > 0 ? "+" : ""}${fmt(d.otif_pts, 1)} pts`],
    ["Cost of the actions", usd(b.action_cost_usd), usd(n.action_cost_usd), usd(n.action_cost_usd - b.action_cost_usd)],
    ["CO2e per TEU, inland moves (K-07)", kg(b.co2e_inland_kg_per_teu), kg(n.co2e_inland_kg_per_teu), b.co2e_inland_kg_per_teu == null ? "—" : "0 kg"],
    ["CO2e added by the actions (air vs sea)", `${fmt(b.co2e_actions_kg)} kg`, `${fmt(n.co2e_actions_kg)} kg`, `${fmt(d.co2e_kg)} kg`],
  ];
  return (
    <div className="flex flex-col gap-4" data-testid="studio">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Orders saved (expected)" value={fmt(d.orders_saved, 1)} />
        <Tile label="OTIF" value={d.otif_pts === null ? "—" : `${d.otif_pts > 0 ? "+" : ""}${fmt(d.otif_pts, 1)} pts`} />
        <Tile
          label="Lateness cost avoided"
          value={usd(d.lateness_cost_avoided_usd)}
          note={`of which quality ${usd(d.of_which_quality_usd)}; cost of actions ${usd(d.action_cost_usd)}`}
        />
        <Tile label="Net value of acting" value={usd(d.net_usd)} tone={d.net_usd >= 0 ? "text-ok" : "text-danger"} />
      </div>
      <Card>
        <CardHeader
          title="With Nexus vs without"
          subtitle={`Same seeded inputs as of ${k.as_of.slice(0, 10)}: do nothing, or accept every action with positive expected value`}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="comparison">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">KPI</th>
                <th className="py-2 pr-3 text-right font-medium">Without Nexus</th>
                <th className="py-2 pr-3 text-right font-medium">With Nexus</th>
                <th className="py-2 pr-3 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map(([label, without, withN, change]) => (
                <tr key={label}>
                  <td className="py-2 pr-3">{label}</td>
                  <td className="tabular py-2 pr-3 text-right">{without}</td>
                  <td className="tabular py-2 pr-3 text-right font-semibold">{withN}</td>
                  <td className="tabular py-2 pr-3 text-right text-muted">{change}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          At the P50 disruption length: production orders late {fmt(k.at_p50.baseline?.production_late ?? 0, 1)} without
          Nexus, {fmt(k.at_p50.nexus_recommended?.production_late ?? 0, 1)} with it.
        </p>
      </Card>
      <Card>
        <CardHeader title="What Nexus did" subtitle={alerts.length ? `For: ${alerts.map((a) => a.title).join(" · ")}` : "No open disruption alerts in this scenario"} />
        <ul className="flex flex-col gap-2" data-testid="actions">
          {actions.map((a) => (
            <li key={a.id} className="rounded-[var(--radius-control)] border border-border p-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="info">{ACTION[a.type] ?? a.type}</Badge>
                <span className="text-xs text-muted">{a.source.toUpperCase()}</span>
                <span className="tabular text-xs">
                  benefit {usd(a.benefit_usd)} · cost {usd(a.cost_usd)} · confidence {fmt((a.confidence ?? 0) * 100)}%
                </span>
              </div>
              {a.rationale ? <p className="mt-1 text-xs text-muted">{a.rationale}</p> : null}
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-xs text-muted">
        Synthetic scenario and fictional firms. Production lateness comes from C1&apos;s cascade on the scenario&apos;s
        open alerts (P90 length for K-05); a reroute saves a gateway-blocked order with Mongla&apos;s feasible share;
        quality uses C5&apos;s options. In-transit lateness is high in both columns because synthetic due dates fall
        ≈ 5 h after the planned delivery, and these actions do not change transit. Rates and costs are estimates
        (model cards: nexus-recommendations, nexus-studio).
      </p>
    </div>
  );
}

export default function ScenarioStudioPage() {
  return (
    <>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="mb-1 text-xl font-semibold tracking-tight">Scenario Studio</h1>
          <p className="text-sm text-muted">What if…, and what should we do? The same shock with and without Nexus&apos;s actions.</p>
        </div>
        <div className="flex items-center gap-2">
          <DataBadge mode="synthetic" sources={["nexus", "c1", "c5"]} />
          <PrintButton />
        </div>
      </div>
      <Suspense fallback={<div className="skeleton h-[600px] w-full" />}>
        <Studio />
      </Suspense>
    </>
  );
}
