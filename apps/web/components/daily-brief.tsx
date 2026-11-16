import Link from "next/link";

import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";

const TONE: Record<string, string> = {
  info: "bg-[var(--series-1)]",
  watch: "bg-[var(--warn)]",
  risk: "bg-[var(--danger)]",
};

/** Today's brief (NX-R05): template sentences over structured rows; every number cites its row. */
export async function DailyBrief() {
  const { data, error } = await (await api()).GET("/api/v1/brief");
  if (error || !data) return <ErrorNote what="today's brief" />;
  const b = data.data;
  return (
    <Card data-testid="daily-brief">
      <CardHeader title={b.title} subtitle="Built from the rows below each sentence; nothing here is free text from the web" />
      <ul className="flex flex-col gap-2 text-sm">
        {b.lines.map((l, i) => (
          <li key={i} className="flex gap-2">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TONE[l.tone] ?? TONE.info}`} aria-label={l.tone} />
            <span>
              {l.text}{" "}
              {l.cites.map((c) => (
                <Link
                  key={`${c.kind}:${c.id}`}
                  href={c.href ?? "#"}
                  title={`${c.kind} ${c.id}`}
                  className="ml-1 inline-block rounded-full border border-border px-1.5 text-[10px] text-muted hover:text-text"
                >
                  {c.label}
                </Link>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
