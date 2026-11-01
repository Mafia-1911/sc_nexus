"use client";

import { AlertTriangle, CheckCircle2, ShieldAlert, Upload, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { inspectImage, loadGallery, loadLot, loadSpc } from "@/app/quality/actions";
import { decide } from "@/app/radar/actions";
import { DataBadge } from "@/components/data-badge";
import { HeatImage } from "@/components/quality/heat-image";
import { SpcChart } from "@/components/quality/spc-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { ACTION, type Item, type Line, type LiveResult, type Lot, type LotDetail, type Meta, type Spc, STATUS, fileUrl, usd } from "@/lib/c5";
import { cn, dhakaTime, fmt } from "@/lib/utils";

type CategoryCard = { method?: string; threshold?: number; licence?: string; encode_ms?: number; metrics?: Record<string, unknown> };
export type Summary = {
  lots: number;
  rejected: number;
  held_for_qa: number;
  orders_at_risk: number;
  lines_alarming: number;
  categories: Record<string, CategoryCard>;
  lot_risk: Record<string, unknown>;
};

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-border bg-surface/85 p-4 shadow-sm backdrop-blur-md">
      <span className="text-xs text-muted">{label}</span>
      <span className="tabular text-2xl font-semibold">{value}</span>
      {detail ? <span className="text-xs text-muted">{detail}</span> : null}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const look = STATUS[status] ?? STATUS.in_process;
  const Icon = status === "released" ? CheckCircle2 : status === "rejected" ? AlertTriangle : ShieldAlert;
  return (
    <Badge tone={look.tone} className="inline-flex items-center gap-1">
      <Icon className="size-3" aria-hidden />
      {look.label}
    </Badge>
  );
}

function pctOf(v: number | null | undefined) {
  return v === null || v === undefined ? "—" : `${fmt(v * 100)} %`;
}

function LotDrawer({ detail, scenario, onClose }: { detail: LotDetail; scenario: string; onClose: () => void }) {
  const [opacity, setOpacity] = useState(0.6);
  const [recs, setRecs] = useState(detail.recommendations);
  const lot = detail.lot;
  const aql = detail.aql as Record<string, number | string | Record<string, number>>;
  const sim = (aql.simulation ?? {}) as Record<string, number>;
  const act = async (id: string, decision: "accepted" | "dismissed") => {
    const out = await decide(scenario, id, decision, null);
    if (out.data) setRecs(recs.map((r) => (r.id === id ? { ...r, status: decision } : r)));
  };
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-2xl flex-col gap-4 overflow-y-auto border-l border-border bg-surface p-5 shadow-xl" data-testid="lot-drawer" aria-label={`Lot ${lot.lot_code}`}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">
            {lot.lot_code} <StatusPill status={lot.status} />
          </h2>
          <p className="text-xs text-muted">
            {lot.product} · {lot.facility}, line {lot.line} (shift {lot.shift}) · {fmt(lot.size_units)} units · made {dhakaTime(lot.produced_at)}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface-2"><X className="size-4" /></button>
      </header>
      <section className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" data-testid="aql">
        <div><div className="text-xs text-muted">Plan (ISO 2859-1)</div><div className="tabular">{String(aql.level)} · AQL {String(aql.aql)} · {String(aql.code_letter)}</div></div>
        <div><div className="text-xs text-muted">Sample · accept / reject</div><div className="tabular">{String(aql.sample_size)} · ≤ {String(aql.accept)} / ≥ {String(aql.reject)}</div></div>
        <div><div className="text-xs text-muted">Flagged by the model</div><div className="tabular">{String(aql.flagged)} <span className="text-xs text-muted">({String(aql.false_alarms)} false alarms)</span></div></div>
        <div><div className="text-xs text-muted">Confirmed defects</div><div className="tabular font-semibold">{String(aql.confirmed_defects)} → {String(aql.decision).replace(/_/g, " ")}</div></div>
      </section>
      <p className="text-[11px] text-muted">
        Assistive: an inspector confirms flagged items. Simulation truth for this synthetic lot: {sim.true_defects_in_sample ?? "—"} defective items in the sample, {sim.missed_by_model ?? "—"} missed by the model.
        {lot.industry === "pharma" ? " Pharma lots are never released automatically: QA decides." : ""}
      </p>
      {detail.alert ? (
        <section className="rounded-[var(--radius-control)] border border-border p-3" data-testid="impact">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="size-4 text-warn" aria-hidden /> {detail.alert.title as string}
          </h3>
          <p className="mt-1 text-xs text-muted">{detail.alert.body as string}</p>
          {detail.order ? (
            <p className="mt-1 text-xs">
              Order <span className="font-medium">{detail.order.reference as string}</span>: {fmt(detail.order.qty as number)} units due {String(detail.order.due_date)} ({usd(detail.order.revenue_usd as number)}).
            </p>
          ) : null}
          <ul className="mt-3 flex flex-col gap-2" data-testid="options">
            {recs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface-2 p-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{ACTION[r.action_type] ?? r.action_type}</div>
                  <div className="text-xs text-muted">{r.rationale}</div>
                </div>
                <div className="tabular text-xs">
                  cost {usd(r.expected_cost_usd)} · benefit {usd(r.expected_benefit_usd)}
                </div>
                <div className="flex gap-1">
                  {(r.action_type === "expedite_air" || r.action_type === "replace_production") && lot.cluster ? (
                    <Link href={`/routes?origin=${lot.cluster}&dest=BDCGP`} className="rounded border border-border px-2 py-0.5 text-xs hover:bg-surface">Replan</Link>
                  ) : null}
                  {r.status === "proposed" ? (
                    <>
                      <button type="button" onClick={() => act(r.id, "accepted")} className="rounded bg-primary px-2 py-0.5 text-xs text-on-primary">Accept</button>
                      <button type="button" onClick={() => act(r.id, "dismissed")} className="rounded border border-border px-2 py-0.5 text-xs">Dismiss</button>
                    </>
                  ) : (
                    <Badge tone={r.status === "accepted" ? "ok" : "neutral"}>{r.status}</Badge>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Inspected items (flagged first)</h3>
          <label className="flex items-center gap-2 text-xs text-muted">
            heatmap
            <input type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Heatmap opacity" />
          </label>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4" data-testid="items">
          {detail.items.map((it) => (
            <HeatImage key={it.id} item={it} opacity={opacity} />
          ))}
        </div>
        <p className="mt-1 text-[11px] text-muted">Each item is a real dataset image ({detail.items[0]?.source_dataset ?? "—"}) mapped to this fictional SKU; the label is that image&apos;s ground truth.</p>
      </section>
    </aside>
  );
}

function LiveInspect({ categories }: { categories: string[] }) {
  const [result, setResult] = useState<LiveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <form
      action={(form) =>
        start(async () => {
          setError(null);
          const out = await inspectImage(form);
          if (out.data) setResult(out.data);
          else setError(out.error ?? "Inspection failed.");
        })
      }
      className="flex flex-col gap-2"
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Category
          <select name="category" className="rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-sm text-text" defaultValue={categories[0]}>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <input type="file" name="image" accept="image/png,image/jpeg" className="text-xs" aria-label="Image to inspect" />
        <button type="submit" disabled={pending} className="inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-primary px-3 py-1.5 text-sm text-on-primary disabled:opacity-60" data-testid="inspect">
          <Upload className="size-4" aria-hidden /> {pending ? "Inspecting…" : "Inspect"}
        </button>
      </div>
      {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
      {result ? (
        <div className="flex items-start gap-3" data-testid="live-result">
          <div className="relative size-40 overflow-hidden rounded-[var(--radius-control)] border border-border">
            {/* eslint-disable-next-line @next/next/no-img-element -- the uploaded image */}
            <img src={fileUrl(result.image_url)} alt="uploaded" className="absolute inset-0 size-full object-cover" />
            {/* eslint-disable-next-line @next/next/no-img-element -- its heatmap */}
            <img src={fileUrl(result.heatmap_url)} alt="" aria-hidden className="absolute inset-0 size-full object-cover opacity-60" />
          </div>
          <dl className="text-sm">
            <dt className="text-xs text-muted">Result</dt>
            <dd>{result.flagged ? <Badge tone="danger">anomaly: send to an inspector</Badge> : <Badge tone="ok">looks normal</Badge>}</dd>
            <dt className="mt-1 text-xs text-muted">Score / threshold</dt>
            <dd className="tabular">{fmt(result.score, 4)} / {fmt(result.threshold, 4)}</dd>
            <dt className="mt-1 text-xs text-muted">Method · CPU time</dt>
            <dd className="tabular">{result.method.replace(/_/g, " ")} · {fmt(result.latency_ms)} ms</dd>
          </dl>
        </div>
      ) : null}
    </form>
  );
}

export function QualityLab({
  summary,
  lots,
  lines,
  gallery,
  scenario,
  meta,
}: {
  summary: Summary;
  lots: Lot[];
  lines: Line[];
  gallery: Item[];
  scenario: string;
  meta: Meta;
}) {
  const [status, setStatus] = useState<string>("all");
  const [industry, setIndustry] = useState<string>("all");
  const [detail, setDetail] = useState<LotDetail | null>(null);
  const [line, setLine] = useState<Line | null>(lines.find((l) => l.alarm_now) ?? lines[0] ?? null);
  const [spc, setSpc] = useState<Spc | null>(null);
  const categories = Object.keys(summary.categories).sort();
  const [category, setCategory] = useState(categories.includes("stitch") ? "stitch" : (categories[0] ?? ""));
  const [images, setImages] = useState(gallery);
  const [opacity, setOpacity] = useState(0.55);
  const [, start] = useTransition();
  const shown = lots.filter((l) => (status === "all" || l.status === status) && (industry === "all" || l.industry === industry));
  const card = summary.categories[category];
  const m = (card?.metrics ?? {}) as Record<string, number>;
  const risk = summary.lot_risk as Record<string, number>;

  const openLot = (id: string) => start(async () => setDetail(await loadLot(id, scenario)));
  const pickLine = (l: Line) => {
    setLine(l);
    setSpc(null);
  };
  useEffect(() => {
    if (!line) return;
    let live = true;
    void loadSpc(line.id, scenario).then((s) => live && setSpc(s));
    return () => {
      live = false;
    };
  }, [line, scenario]);
  const pickCategory = (c: string) => {
    setCategory(c);
    start(async () => setImages(await loadGallery(c)));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted">{meta.note}</p>
        <DataBadge mode={meta.mode} sources={meta.sources} asOf={meta.as_of} modes={meta.modes} />
      </div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5" data-testid="quality-kpis">
        <Tile label="Lots inspected (3 weeks)" value={fmt(summary.lots)} />
        <Tile label="Rejected (garments)" value={fmt(summary.rejected)} detail="failed AQL 2.5 on confirmed defects" />
        <Tile label="Held for QA (pharma)" value={fmt(summary.held_for_qa)} detail="never released automatically" />
        <Tile label="Orders at risk" value={fmt(summary.orders_at_risk)} detail="a failed lot blocks the order" />
        <Tile label="Lines alarming (SPC)" value={fmt(summary.lines_alarming)} detail={`lot-risk Brier ${fmt(risk.brier, 3)} vs ${fmt(risk.brier_base_rate, 3)} base rate`} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            title="Lot board"
            subtitle="Final QC of finished-goods lots: AQL decision on confirmed defects; risk = forecast before inspection"
            aside={
              <div className="flex gap-2 text-xs">
                <select value={industry} onChange={(e) => setIndustry(e.target.value)} aria-label="Industry" className="rounded border border-border bg-surface px-1 py-0.5">
                  <option value="all">all</option>
                  <option value="garments">garments</option>
                  <option value="pharma">pharma</option>
                </select>
                <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status" className="rounded border border-border bg-surface px-1 py-0.5">
                  <option value="all">all statuses</option>
                  <option value="rejected">rejected</option>
                  <option value="quarantine">QA review</option>
                  <option value="released">released</option>
                </select>
              </div>
            }
          />
          <div className="max-h-[460px] overflow-auto">
            <table className="w-full text-sm" data-testid="lot-board">
              <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
                <tr>
                  <th className="py-1.5 pr-2 font-medium">Lot</th>
                  <th className="py-1.5 pr-2 font-medium">Product · plant, line</th>
                  <th className="py-1.5 pr-2 font-medium">Made</th>
                  <th className="py-1.5 pr-2 font-medium">Status</th>
                  <th className="py-1.5 pr-2 font-medium">Defects</th>
                  <th className="py-1.5 pr-2 font-medium">Risk before</th>
                  <th className="py-1.5 pr-2 font-medium">Order</th>
                </tr>
              </thead>
              <tbody>
                {shown.slice(0, 120).map((l) => (
                  <tr key={l.id} onClick={() => openLot(l.id)} className={cn("cursor-pointer border-t border-border hover:bg-surface-2", l.alert_id ? "font-medium" : "")} data-lot={l.id}>
                    <td className="py-1.5 pr-2 font-mono text-xs">{l.lot_code}</td>
                    <td className="py-1.5 pr-2 text-xs">{l.product} · <span className="text-muted">{l.facility.split(" – ")[0]}, {l.line}</span></td>
                    <td className="py-1.5 pr-2 text-xs">{dhakaTime(l.produced_at)}</td>
                    <td className="py-1.5 pr-2"><StatusPill status={l.status} /></td>
                    <td className="tabular py-1.5 pr-2 text-xs">{l.confirmed_defects ?? "—"} / ≤ {l.accept ?? "—"} <span className="text-muted">of {l.sample_size}</span></td>
                    <td className="tabular py-1.5 pr-2 text-xs">{pctOf(l.risk_before)}</td>
                    <td className="py-1.5 pr-2 text-xs">{l.order_ref ? `${l.order_ref} · ${l.order_due}` : "stock"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Lines" subtitle="P(next lot fails AQL), beta-binomial; SPC alarm state" />
          <ul className="mb-3 flex flex-col gap-1 text-sm" data-testid="lines">
            {lines.slice(0, 8).map((l) => (
              <li key={l.id}>
                <button type="button" onClick={() => pickLine(l)} className={cn("flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-surface-2", line?.id === l.id ? "bg-surface-2" : "")}>
                  <span className="truncate text-xs">{l.facility.split(" – ")[0]} · {l.line}</span>
                  <span className="flex items-center gap-2">
                    {l.alarm_now ? <Badge tone="warn">alarm</Badge> : null}
                    <span className="tabular text-xs">{pctOf(l.p_fail_next)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {spc ? <SpcChart spc={spc} /> : <div className="skeleton h-48 w-full" />}
        </Card>
      </div>
      <Card>
        <CardHeader
          title="Images and the model"
          subtitle="Real dataset test images with their heatmaps; upload one to score it live (few-shot, CPU)"
          aside={
            <label className="flex items-center gap-2 text-xs text-muted">
              heatmap
              <input type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Gallery heatmap opacity" />
            </label>
          }
        />
        <div className="mb-3 flex flex-wrap items-center gap-2" role="tablist">
          {categories.map((c) => (
            <button key={c} type="button" role="tab" aria-selected={c === category} onClick={() => pickCategory(c)} className={cn("rounded-full border px-3 py-0.5 text-xs", c === category ? "border-primary bg-primary text-on-primary" : "border-border")}>
              {c}
            </button>
          ))}
          {card ? (
            <span className="ml-auto text-xs text-muted" data-testid="model-card">
              {String(card.method ?? "").replace(/_/g, " ")} · AUROC {fmt(m.image_auroc, 3)} · recall {fmt((m.recall_at_fpr ?? 0) * 100)} % at the 5 % FPR threshold · {card.licence}
              {card.licence?.includes("NC") ? <Badge tone="warn" className="ml-1">non-commercial</Badge> : null}
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6 xl:grid-cols-8" data-testid="gallery">
          {images.slice(0, 16).map((it) => (
            <HeatImage key={it.id} item={it} opacity={opacity} />
          ))}
        </div>
        <div className="mt-4 border-t border-border pt-3">
          <LiveInspect categories={categories} />
        </div>
      </Card>
      {detail ? <LotDrawer key={detail.lot.id} detail={detail} scenario={scenario} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}
