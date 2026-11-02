"use client";

import { Printer } from "lucide-react";

/** One-page export (01-product §5 step 8): the browser's print dialog, "Save as PDF". */
export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border border-border px-3 py-1 text-xs print:hidden"
      data-testid="print"
    >
      <Printer className="size-3.5" aria-hidden />
      Export one page (PDF)
    </button>
  );
}
