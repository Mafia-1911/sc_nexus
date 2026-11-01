"use client";

import { ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";

import { decide } from "@/app/radar/actions";
import { DataBadge } from "@/components/data-badge";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { productName, usd } from "@/lib/c1";
import { type EventDetail, type Rec, highlight, hours, typeName } from "@/lib/c2";
import { dhakaTime, fmt } from "@/lib/utils";

function Recommendation({ rec, scenario }: { rec: Rec; scenario: string }) {
  const [state, setState] = useState(rec);
  const [pending, start] = useTransition();
  const act = (decision: "accepted" | "dismissed") =>
    start(async () => {
      const out = await decide(scenario, state.id, decision, null);
      if (out.data) setState(out.data);
    });
  const targets = state.targets as { facility: string; product: string; units: number; days_of_cover: number; cost_usd: number }[];
  const ev = (state.expected_benefit_usd ?? 0) - (state.expected_cost_usd ?? 0);
  return (
    <section className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-primary/40 bg-primary/5 p-3" data-testid="buffer-rec">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Raise the buffer (recommendation)</h3>
        <Badge tone={state.status === "accepted" ? "ok" : state.status === "dismissed" ? "neutral" : "info"}>{state.status}</Badge>
      </div>
      <p className="text-xs">{state.rationale}</p>
      <dl className="grid grid-cols-4 gap-2 text-xs">
        {[
          ["Expected benefit", usd(state.expected_benefit_usd)],
          ["Holding cost", usd(state.expected_cost_usd)],
          ["Net value", usd(ev)],
          ["Confidence", fmt((state.confidence ?? 0) * 100) + "%"],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted">{k}</dt>
            <dd className="tabular font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      <table className="w-full text-xs">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1 font-medium">Plant</th>
            <th className="py-1 font-medium">Input</th>
            <th className="py-1 text-right font-medium">Extra units</th>
            <th className="py-1 text-right font-medium">Days of cover</th>
          </tr>
        </thead>
        <tbody>
          {targets.slice(0, 6).map((t) => (
            <tr key={`${t.facility}:${t.product}`} className="border-t border-border">
              <td className="max-w-48 truncate py-1" title={t.facility}>{t.facility}</td>
              <td className="py-1">{productName(t.product)}</td>
              <td className="tabular py-1 text-right">{fmt(t.units)}</td>
              <td className="tabular py-1 text-right">{fmt(t.days_of_cover, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] text-muted">
        Safety stock z·√(L·σd² + d²·σL²) with lead time inflated by the event; holding 25 %/yr and a 15 % lateness cost are
        estimates. Synthetic plants and orders.
      </p>
      {state.status === "proposed" ? (
        <div className="flex gap-2">
          <button type="button" disabled={pending} onClick={() => act("accepted")} className="rounded-[var(--radius-control)] bg-primary px-3 py-1 text-xs font-medium text-on-primary">
            Accept
          </button>
          <button type="button" disabled={pending} onClick={() => act("dismissed")} className="rounded-[var(--radius-control)] border border-border px-3 py-1 text-xs">
            Dismiss
          </button>
        </div>
      ) : null}
    </section>
  );
}

type Signal = { kind: string; label: string; contribution: number };
type Check = { kind: string; label: string };

export function EventDrawer({ detail, scenario, onClose }: { detail: EventDetail; scenario: string; onClose: () => void }) {
  const e = detail.event;
  return (
    <Card className="flex flex-col gap-4" data-testid="event-drawer">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">{e.title}</h2>
          <p className="text-xs text-muted">
            {typeName(e.type)} · {e.status} · from {dhakaTime(e.start_est)} · lasts {hours(e.duration_p50_h)} (P90{" "}
            {hours(e.duration_p90_h)})
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close event" className="rounded-[var(--radius-control)] p-1 text-muted hover:bg-surface-2">
          <X className="size-4" aria-hidden />
        </button>
      </header>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span>
          Severity <strong className="tabular">{fmt((e.severity ?? 0) * 100)}</strong>
        </span>
        <span>
          Confidence <strong className="tabular">{fmt((e.confidence ?? 0) * 100)}%</strong>
          {e.confidence_fused != null && e.confidence_fused !== e.confidence ? (
            <>
              {" "}
              → <strong className="tabular text-ok">{fmt(e.confidence_fused * 100)}%</strong> fused
            </>
          ) : null}
        </span>
        <span>{e.mentions} report(s)</span>
        {e.locodes.map((l) => (
          <Badge key={l} tone="info">{l}</Badge>
        ))}
        <DataBadge mode={e.data_mode} sources={[e.source_id]} />
      </div>
      {e.corroboration?.length || e.fusion_checks?.length ? (
        <section data-testid="corroboration">
          <h3 className="mb-1.5 text-xs font-semibold text-muted">
            Corroborated by (log-odds added to the news confidence)
          </h3>
          <ul className="flex flex-wrap gap-2">
            {((e.corroboration ?? []) as Signal[]).map((s, i) => (
              <li key={i}>
                <Badge tone={s.kind === "news" ? "info" : "ok"} title={s.label}>
                  {s.kind}: {s.label.length > 48 ? `${s.label.slice(0, 47)}…` : s.label} · +
                  {s.contribution.toFixed(2)}
                </Badge>
              </li>
            ))}
          </ul>
          {((e.fusion_checks ?? []) as Check[]).map((c, i) => (
            <p key={i} className="mt-1 text-xs text-muted">
              {c.kind}: {c.label}
            </p>
          ))}
        </section>
      ) : null}
      {detail.mentions.length ? (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted">Evidence (highlighted spans are what the extractor used)</h3>
          <ul className="flex flex-col gap-2" data-testid="evidence">
            {detail.mentions.map((m) => (
              <li key={m.article_id} className="rounded-[var(--radius-control)] border border-border p-2 text-sm">
                <p>
                  {highlight(m.text, m.evidence as Record<string, unknown[]>).map((part, i) =>
                    part.mark ? (
                      <mark key={i} title={part.mark} className="rounded bg-warn/20 px-0.5 text-text">
                        {part.text}
                      </mark>
                    ) : (
                      <span key={i}>{part.text}</span>
                    ),
                  )}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span>{m.outlet}</span>
                  <span>{dhakaTime(m.published_at)}</span>
                  <span>{m.extractor}</span>
                  {m.llm_agrees === false ? <Badge tone="warn">LLM disagrees</Badge> : null}
                  {m.llm_agrees ? <Badge tone="ok">LLM agrees</Badge> : null}
                  <a href={m.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-info hover:underline">
                    source <ExternalLink className="size-3" aria-hidden />
                  </a>
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-xs text-muted">{e.summary}</p>
      )}
      {detail.linked_facilities.length ? (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted">Plants in the affected area (this scenario)</h3>
          <p className="text-xs">
            {detail.linked_facilities.slice(0, 8).map((f, i) => (
              <span key={String(f.facility_id)}>
                {i ? ", " : ""}
                <Link className="text-info hover:underline" href="/network">{String(f.name)}</Link>
              </span>
            ))}
            {detail.linked_facilities.length > 8 ? ` and ${detail.linked_facilities.length - 8} more` : ""}
          </p>
        </section>
      ) : null}
      {detail.recommendations.map((r) => (
        <Recommendation key={r.id} rec={r} scenario={scenario} />
      ))}
      {e.locodes.includes("BDCGP") ? (
        <p className="text-xs text-muted">
          Chattogram is the network&apos;s top single point of failure: see its TTS vs TTR in{" "}
          <Link className="text-info hover:underline" href="/network">Supplier Network</Link>.
        </p>
      ) : null}
    </Card>
  );
}
