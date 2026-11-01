"use client";

import { Badge } from "@/components/ui/badge";
import { type Item, fileUrl } from "@/lib/c5";
import { cn, fmt } from "@/lib/utils";

/** A real dataset image with the model's heatmap on top (opacity from the parent's slider). */
export function HeatImage({ item, opacity, showTruth = true }: { item: Item; opacity: number; showTruth?: boolean }) {
  const truth = item.label && item.label !== "good" ? item.label.replace(/_/g, " ") : "good";
  return (
    <figure className={cn("overflow-hidden rounded-[var(--radius-control)] border bg-surface-2", item.flagged ? "border-danger" : "border-border")} data-flagged={item.flagged}>
      <div className="relative aspect-square">
        {/* eslint-disable-next-line @next/next/no-img-element -- proxied dataset images, sizes vary */}
        <img src={fileUrl(item.image_url)} alt={`${item.category} image, ${truth}`} className="absolute inset-0 size-full object-cover" loading="lazy" />
        {item.heatmap_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- heatmap overlay
          <img src={fileUrl(item.heatmap_url)} alt="" aria-hidden className="absolute inset-0 size-full object-cover" style={{ opacity }} loading="lazy" />
        ) : null}
      </div>
      <figcaption className="flex items-center justify-between gap-1 px-1.5 py-1 text-[10px]">
        <span className="tabular">{fmt(item.score / item.threshold, 2)}× thr.</span>
        {item.flagged ? <Badge tone="danger">flagged</Badge> : <span className="text-muted">clear</span>}
        {showTruth ? <span className="truncate text-muted" title={`ground truth: ${truth} · ${item.source_dataset}`}>{truth}</span> : null}
      </figcaption>
    </figure>
  );
}
