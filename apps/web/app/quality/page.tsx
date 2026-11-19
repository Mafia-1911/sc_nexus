import { Suspense } from "react";

import { QualityInspector } from "@/components/quality/quality-inspector";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Quality Lab");

export default function QualityLabPage() {
  return (
    <>
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-text">Quality Lab</h1>
        <p className="mt-0.5 text-sm text-muted">
          Manufacturing defect intelligence: zero-shot visual anomaly detection, localized heatmaps, and batch QA
          screening.
        </p>
      </div>

      <Suspense fallback={<div className="skeleton h-[600px] w-full" />}>
        <QualityInspector />
      </Suspense>
    </>
  );
}
