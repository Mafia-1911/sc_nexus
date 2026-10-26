import { connection } from "next/server";
import { Suspense } from "react";

import { Card, CardHeader } from "@/components/ui/card";

async function Connection() {
  await connection();
  return null;
}

/** Marks the page as request-time on purpose: its title carries the runtime brand
 *  (Next 16 "generateMetadata with Cache Components"). Renders nothing. */
function DynamicMarker() {
  return (
    <Suspense>
      <Connection />
    </Suspense>
  );
}

/** A designed empty state for pages whose capability lands in a later milestone (05 §3). */
export function ComingSoon({
  title,
  question,
  milestone,
  items,
}: {
  title: string;
  question: string;
  milestone: string;
  items: string[];
}) {
  return (
    <>
      <DynamicMarker />
      <h1 className="mb-1 text-xl font-semibold tracking-tight">{title}</h1>
      <p className="mb-4 text-sm text-muted">{question}</p>
      <Card className="max-w-2xl">
        <CardHeader title={`Arrives in ${milestone}`} subtitle="The data model, API contract and synthetic world it needs are in place." />
        <ul className="list-disc pl-5 text-sm text-muted">
          {items.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      </Card>
    </>
  );
}
