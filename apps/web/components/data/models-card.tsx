import { ErrorNote } from "@/components/kpi-strip";
import { Card, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";

export async function ModelsCard() {
  const { data, error } = await (await api()).GET("/api/v1/models");
  if (error || !data) return <ErrorNote what="models" />;
  return (
    <Card>
      <CardHeader title="Models" subtitle="Each model ships with a baseline, a card and a time-based evaluation" />
      {data.data.length === 0 ? (
        <p className="text-sm text-muted">
          No models registered yet. Baselines register from M3 (C1), each with a model card; a complex model
          replaces its baseline only if it beats it on a time-based holdout (AGENTS.md rule 5).
        </p>
      ) : (
        <ul className="text-sm">
          {data.data.map((m) => (
            <li key={`${m.capability}-${m.name}-${m.version}`}>
              {m.capability} · {m.name} {m.version}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
