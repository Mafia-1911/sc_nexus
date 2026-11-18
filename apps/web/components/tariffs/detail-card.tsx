"use client";

import { ExternalLink, Info, X } from "lucide-react";

import { DataBadge } from "@/components/data-badge";
import { RateStack } from "@/components/tariffs/rate-stack";
import { Card, CardFooter } from "@/components/ui/card";
import { type LineRate, type ProductDetail, type TariffOverview, ROLE_LABEL, countryName, pct } from "@/lib/c6";
import { cn, dhakaTime } from "@/lib/utils";

function summary(lines: LineRate[]) {
  const resolved = lines.filter((l) => l.is_resolved && l.effective_pct !== null && l.effective_pct !== undefined);
  const values = resolved.map((l) => l.effective_pct as number);
  const rep = resolved.length ? resolved.reduce((a, b) => ((b.effective_pct ?? 0) > (a.effective_pct ?? 0) ? b : a)) : lines[0];
  return {
    rep,
    allResolved: lines.length > 0 && resolved.length === lines.length,
    lo: values.length ? Math.min(...values) : null,
    hi: values.length ? Math.max(...values) : null,
  };
}

function rangeText(s: ReturnType<typeof summary>): string {
  if (!s.rep) return "—";
  if (!s.allResolved) return `≥ ${pct(s.rep.base_pct ?? null).replace("Free", "0%")}`;
  return s.lo === s.hi ? pct(s.hi) : `${pct(s.lo).replace("Free", "0%")}–${pct(s.hi)}`;
}

/** One surcharge: "+10%". Several whose stacking the lines do not state: "up to +66.5% (4)". */
function surchargeText(rep: LineRate | undefined): string {
  if (!rep?.additional_pct) return "—";
  const n = rep.components.filter((c) => c.role === "additional").length;
  return n > 1 ? `up to +${pct(rep.additional_pct)} (${n} lines)` : `+${pct(rep.additional_pct)}`;
}

/** Lines that share a rate collapse into one row ("6 lines at 16.5%"). */
function grouped(lines: LineRate[]) {
  const by = new Map<string, LineRate[]>();
  for (const l of lines) {
    const key = l.is_resolved ? pct(l.effective_pct ?? null) : "no single number";
    by.set(key, [...(by.get(key) ?? []), l]);
  }
  return [...by.entries()];
}

export function DetailCard({
  detail,
  origin,
  overview,
  onOrigin,
  onClose,
}: {
  detail: ProductDetail;
  origin: string;
  overview: TariffOverview;
  onOrigin: (iso3: string) => void;
  onClose: () => void;
}) {
  const market = detail.markets[0];
  const marketName = overview.markets.find((m) => m.code === market?.market)?.name ?? market?.market;
  const mine = market?.lines.filter((l) => l.origin === origin) ?? [];
  const s = summary(mine);
  const rep = s.rep;
  const duty = rep ? (rep.preference_pct ?? rep.base_pct) : null;
  const modes = Object.keys(detail.data_modes);
  return (
    <Card className="flex flex-col gap-4" data-testid="tariff-detail">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">{detail.product.name}</h2>
          <p className="text-xs text-muted">
            HS {detail.product.hs6} · into {marketName} · from {countryName(overview.origins, origin)} · as of {detail.as_of}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close product details" className="rounded-[var(--radius-control)] p-1 text-muted hover:bg-surface-2">
          <X className="size-4" aria-hidden />
        </button>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">What this origin pays</h3>
          <p className="tabular text-2xl font-semibold" data-testid="detail-rate">
            {rangeText(s)}
            {mine.length > 1 ? <span className="ml-2 text-sm font-normal text-muted">over {mine.length} national lines</span> : null}
          </p>
          {rep ? (
            <RateStack base={rep.base_pct} duty={duty} surcharge={rep.additional_pct} resolved={rep.is_resolved} />
          ) : (
            <p className="text-sm text-muted">No tariff line for this product in this market.</p>
          )}
          {rep?.notes.length ? (
            <ul className="flex flex-col gap-1 text-xs" data-testid="detail-notes">
              {rep.notes.map((n) => (
                <li key={n} className="flex gap-2">
                  <Info className="mt-0.5 size-3.5 shrink-0 text-info" aria-hidden />
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Compare origins in {marketName}</h3>
          <table className="w-full text-xs" data-testid="detail-compare">
            <thead>
              <tr className="text-left text-muted">
                <th scope="col" className="py-1 font-medium">Origin</th>
                <th scope="col" className="py-1 font-medium">Pays</th>
                <th scope="col" className="py-1 font-medium">Base</th>
                <th scope="col" className="py-1 font-medium">Preference</th>
                <th scope="col" className="py-1 font-medium">Surcharge</th>
              </tr>
            </thead>
            <tbody>
              {detail.origins.map((o) => {
                const lines = market?.lines.filter((l) => l.origin === o) ?? [];
                const os = summary(lines);
                return (
                  <tr key={o} className={cn("border-t border-border", o === origin && "bg-surface-2")}>
                    <td className="py-1">
                      <button type="button" onClick={() => onOrigin(o)} className="text-left underline-offset-2 hover:underline" aria-pressed={o === origin}>
                        {countryName(overview.origins, o)}
                      </button>
                    </td>
                    <td className="tabular py-1 font-semibold">{rangeText(os)}</td>
                    <td className="tabular py-1">{pct(os.rep?.base_pct ?? null)}</td>
                    <td className="tabular py-1">{os.rep?.preference_pct === null || os.rep?.preference_pct === undefined ? "—" : pct(os.rep.preference_pct)}</td>
                    <td className="tabular py-1">{surchargeText(os.rep)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>

      {rep ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">How the rate is made up</h3>
          <table className="w-full text-xs" data-testid="detail-components">
            <thead>
              <tr className="text-left text-muted">
                <th scope="col" className="py-1 font-medium">Rule</th>
                <th scope="col" className="py-1 font-medium">Reference</th>
                <th scope="col" className="py-1 font-medium">Duty text (verbatim)</th>
                <th scope="col" className="py-1 font-medium">In force</th>
                <th scope="col" className="py-1 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {rep.components.map((c, i) => (
                <tr key={`${c.measure_ref}:${c.role}:${i}`} className="border-t border-border align-top">
                  <td className="py-1 pr-2">
                    <span className="font-medium">{ROLE_LABEL[c.role] ?? c.role}</span>
                    {c.origin_name && c.origin_code !== "*" ? (
                      <span className="block">
                        {c.origin_name}
                        {c.origin_name !== c.origin_code ? <span className="text-muted"> ({c.origin_code})</span> : null}
                      </span>
                    ) : null}
                    {c.note ? <span className="block text-muted">{c.note}</span> : null}
                  </td>
                  <td className="tabular py-1 pr-2">
                    {c.measure_ref}
                    {c.legal_ref && c.legal_ref !== `HTSUS ${c.measure_ref}` ? <span className="block text-muted">{c.legal_ref}</span> : null}
                  </td>
                  <td className="py-1 pr-2">{c.duty_text || "—"}</td>
                  <td className="tabular py-1 pr-2">{c.valid_from ? `from ${c.valid_from}` : "—"}{c.valid_to ? ` to ${c.valid_to}` : ""}</td>
                  <td className="py-1">
                    {c.source_url ? (
                      <a href={c.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                        {c.source_id}
                        <ExternalLink className="size-3" aria-hidden />
                      </a>
                    ) : (
                      c.source_id
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">National lines</h3>
          <table className="w-full text-xs" data-testid="detail-lines">
            <tbody>
              {grouped(mine).map(([rate, lines]) => (
                <tr key={rate} className="border-t border-border align-top">
                  <td className="tabular w-28 py-1 font-semibold">{rate}</td>
                  <td className="py-1">
                    {lines.length} line{lines.length > 1 ? "s" : ""}: {lines.slice(0, 4).map((l) => `${l.code}${l.description ? ` ${l.description}` : ""}`).join("; ")}
                    {lines.length > 4 ? ` and ${lines.length - 4} more` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Changes for this product</h3>
          {market?.changes.length ? (
            <ul className="flex flex-col gap-1 text-xs">
              {market.changes.map((c) => (
                <li key={c.id}>
                  <span className="tabular">{dhakaTime(c.detected_at)}</span> · {c.measure_ref} ({c.origin_code}) {c.change}:{" "}
                  {c.old_duty_text ?? "—"} → {c.new_duty_text ?? "—"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">No change detected since the first daily fetch.</p>
          )}
        </section>
      </div>

      <CardFooter>
        <DataBadge mode={modes.length === 1 ? modes[0] : modes.length ? "mixed" : "none"} sources={detail.sources} modes={detail.data_modes} />
        <span>{detail.sources.join(", ")}</span>
        <span className="italic">Preferences assume the rules of origin are met. Information, not legal or customs advice.</span>
      </CardFooter>
    </Card>
  );
}
