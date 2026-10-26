import { DataBadge } from "@/components/data-badge";
import { api } from "@/lib/api/server";
import { fmt } from "@/lib/utils";

/** KPI strip (05 §4 Control Tower): value + unit + detail + its own data badge. */
export async function KpiStrip({ scenario }: { scenario: string }) {
  const { data, error } = await (await api()).GET("/api/v1/kpis", { params: { query: { scenario } } });
  if (error || !data) return <ErrorNote what="KPIs" />;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5" data-testid="kpi-strip">
      {data.data.kpis.map((k) => (
        <div key={k.key} className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-border bg-surface p-4" data-kpi={k.key}>
          <span className="text-xs text-muted">{k.label}</span>
          <span className="tabular text-2xl font-semibold">
            {typeof k.value === "number" ? fmt(k.value, Number.isInteger(k.value) ? 0 : 1) : "—"}
            {k.unit && typeof k.value === "number" ? <span className="ml-1 text-sm font-normal text-muted">{k.unit}</span> : null}
          </span>
          {k.detail ? <span className="text-xs text-muted">{k.detail}</span> : null}
          <span className="mt-auto pt-1">
            <DataBadge mode={k.meta.mode} sources={k.meta.sources} asOf={k.meta.as_of} modes={k.meta.modes} />
          </span>
        </div>
      ))}
    </div>
  );
}

export function ErrorNote({ what }: { what: string }) {
  return (
    <p role="alert" className="rounded-[var(--radius-control)] border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
      Could not load {what} from the API. Is it running (`make api` or `make up`)?
    </p>
  );
}
