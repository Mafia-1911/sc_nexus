/* eslint-disable @next/next/no-img-element */
"use client";

import { useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Eye,
  FileSearch,
  HelpCircle,
  Layers,
  Loader2,
  SlidersHorizontal,
  UploadCloud,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface InspectionResponse {
  category: string;
  domain: string;
  anomaly_score: number;
  threshold: number;
  is_anomalous: boolean;
  verdict: string;
  severity: string;
  model_name: string;
  model_mode: string;
  device: string;
  latency_ms: number;
  heatmap_base64?: string;
  disclaimer: string;
}

interface SamplePreset {
  id: string;
  category: "zipper" | "capsule";
  label: string;
  type: "Normal" | "Defective";
  defectName: string;
  path: string;
  defaultThreshold: number;
}

const BENCHMARK_SAMPLES: SamplePreset[] = [
  {
    id: "zipper_defect",
    category: "zipper",
    label: "Zipper Defect",
    type: "Defective",
    defectName: "Broken Teeth",
    path: "/samples/quality/zipper_defect.png",
    defaultThreshold: 0.415,
  },
  {
    id: "zipper_good",
    category: "zipper",
    label: "Zipper Flawless",
    type: "Normal",
    defectName: "None (Nominal)",
    path: "/samples/quality/zipper_good.png",
    defaultThreshold: 0.415,
  },
  {
    id: "capsule_defect",
    category: "capsule",
    label: "Capsule Defect",
    type: "Defective",
    defectName: "Surface Crack",
    path: "/samples/quality/capsule_defect.png",
    defaultThreshold: 0.32,
  },
  {
    id: "capsule_good",
    category: "capsule",
    label: "Capsule Flawless",
    type: "Normal",
    defectName: "None (Nominal)",
    path: "/samples/quality/capsule_good.png",
    defaultThreshold: 0.32,
  },
];

const DEFAULT_THRESHOLDS: Record<string, number> = {
  zipper: 0.415,
  capsule: 0.32,
};

export function QualityInspector() {
  const [category, setCategory] = useState<"zipper" | "capsule">("zipper");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(BENCHMARK_SAMPLES[0].path);
  const [customThreshold, setCustomThreshold] = useState<number>(DEFAULT_THRESHOLDS.zipper);
  const [overrideThreshold, setOverrideThreshold] = useState<boolean>(false);
  const [activePreset, setActivePreset] = useState<string | null>(BENCHMARK_SAMPLES[0].id);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InspectionResponse | null>(null);
  const [viewMode, setViewMode] = useState<"side-by-side" | "heatmap" | "original">("side-by-side");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectPreset = (preset: SamplePreset) => {
    setError(null);
    setActivePreset(preset.id);
    setCategory(preset.category);
    setSelectedFile(null);
    setPreviewUrl(preset.path);
    setResult(null);
    if (!overrideThreshold) {
      setCustomThreshold(preset.defaultThreshold);
    }
  };

  const handleCategoryChange = (newCat: "zipper" | "capsule") => {
    setCategory(newCat);
    if (!overrideThreshold) {
      setCustomThreshold(DEFAULT_THRESHOLDS[newCat]);
    }
    const preset = BENCHMARK_SAMPLES.find((s) => s.category === newCat);
    if (preset) {
      selectPreset(preset);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setError(null);
      setActivePreset(null);
      setSelectedFile(file);
      setResult(null);
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    }
  };

  const runInspection = async () => {
    setIsLoading(true);
    setError(null);

    try {
      let fileToInspect = selectedFile;
      if (!fileToInspect && previewUrl) {
        const res = await fetch(previewUrl);
        if (!res.ok) throw new Error(`Failed to load preset image: ${res.statusText}`);
        const blob = await res.blob();
        fileToInspect = new File([blob], `${activePreset || "sample"}.png`, { type: "image/png" });
      }

      if (!fileToInspect) {
        throw new Error("Please select or upload an image first.");
      }

      const formData = new FormData();
      formData.append("file", fileToInspect);
      formData.append("category", category);
      if (overrideThreshold) {
        formData.append("threshold", customThreshold.toString());
      }

      const response = await fetch("/api/quality/inspect", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || errorData.error || `HTTP ${response.status}`);
      }

      const envelope = await response.json();
      setResult(envelope.data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Inspection failed: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  const heatmapSrc = result?.heatmap_base64
    ? result.heatmap_base64.startsWith("data:")
      ? result.heatmap_base64
      : `data:image/png;base64,${result.heatmap_base64}`
    : null;

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner / Domain Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius-card)] border border-border bg-surface p-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold tracking-tight text-text">Universal Quality AI</span>
            <Badge tone="info">Capability C5</Badge>
            <Badge tone="neutral">Zero-Shot WinCLIP</Badge>
          </div>
          <p className="mt-1 text-xs text-muted">
            Zero-shot visual screening and anomaly localization for garment hardware and pharmaceutical batches on the
            Chattogram–Dhaka corridor.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="flex items-center gap-1">
            <Cpu className="size-3.5 text-primary" /> Backbone: OpenAI ViT-B/16+
          </span>
          <span className="text-border">|</span>
          <span className="flex items-center gap-1">
            <Layers className="size-3.5 text-primary" /> k_shot = 0
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Controls and Input (5 cols) */}
        <div className="flex flex-col gap-5 lg:col-span-5">
          {/* Step 1: Category Selection */}
          <Card>
            <CardHeader
              title="1. Product Domain & Category"
              subtitle="Select product type for zero-shot prompt ensembling"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleCategoryChange("zipper")}
                className={cn(
                  "flex flex-col items-start gap-1 rounded-[var(--radius-control)] border p-3 text-left transition-colors",
                  category === "zipper"
                    ? "border-primary bg-primary/10 text-text"
                    : "border-border bg-surface-2 text-muted hover:border-border-strong hover:text-text",
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide">Zipper</span>
                  {category === "zipper" && <CheckCircle2 className="size-4 text-primary" />}
                </div>
                <span className="text-[11px] text-muted">Garments & Apparel Hardware</span>
                <span className="text-[10px] text-muted">Baseline Thresh: {DEFAULT_THRESHOLDS.zipper}</span>
              </button>

              <button
                type="button"
                onClick={() => handleCategoryChange("capsule")}
                className={cn(
                  "flex flex-col items-start gap-1 rounded-[var(--radius-control)] border p-3 text-left transition-colors",
                  category === "capsule"
                    ? "border-primary bg-primary/10 text-text"
                    : "border-border bg-surface-2 text-muted hover:border-border-strong hover:text-text",
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide">Capsule</span>
                  {category === "capsule" && <CheckCircle2 className="size-4 text-primary" />}
                </div>
                <span className="text-[11px] text-muted">Pharma & Healthcare</span>
                <span className="text-[10px] text-muted">Baseline Thresh: {DEFAULT_THRESHOLDS.capsule}</span>
              </button>
            </div>
          </Card>

          {/* Step 2: Benchmark Samples Quick-Pick */}
          <Card>
            <CardHeader
              title="2. Quick-Pick Benchmark Samples"
              subtitle="Verified MVTec AD samples (CC BY-NC-SA 4.0)"
            />
            <div className="grid grid-cols-2 gap-2">
              {BENCHMARK_SAMPLES.map((s) => {
                const isSelected = activePreset === s.id;
                const isCurrentCategory = s.category === category;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => selectPreset(s)}
                    className={cn(
                      "flex items-center gap-2.5 rounded-[var(--radius-control)] border p-2 text-left transition-all",
                      isSelected
                        ? "border-primary bg-primary/10 shadow-xs"
                        : isCurrentCategory
                          ? "border-border bg-surface hover:border-border-strong"
                          : "border-border/60 bg-surface/50 opacity-60 hover:opacity-100",
                    )}
                  >
                    <div className="relative size-10 shrink-0 overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface-2">
                      <img src={s.path} alt={s.label} className="size-full object-cover" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-xs font-medium text-text">{s.label}</span>
                      </div>
                      <div className="flex items-center gap-1 text-[10px]">
                        <span className={cn(s.type === "Defective" ? "text-warn font-semibold" : "text-ok")}>
                          {s.type}
                        </span>
                        <span className="text-muted truncate">({s.defectName})</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>

          {/* Step 3: Custom Upload & Threshold Adjustment */}
          <Card>
            <CardHeader
              title="3. Custom Inspection & Calibration"
              subtitle="Upload your own inspection image or fine-tune sensitivity"
            />
            <div className="flex flex-col gap-3">
              {/* File upload trigger */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg"
                onChange={handleFileChange}
                className="hidden"
                id="quality-file-input"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center justify-center gap-2 rounded-[var(--radius-control)] border border-dashed border-border py-3 text-xs font-medium text-muted transition-colors hover:border-primary hover:bg-surface-2 hover:text-text"
              >
                <UploadCloud className="size-4 text-primary" />
                {selectedFile ? `Change File: ${selectedFile.name}` : "Upload Custom Product Image (PNG/JPG)"}
              </button>

              {/* Threshold Calibration Toggle */}
              <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <SlidersHorizontal className="size-3.5 text-primary" />
                    <span className="text-xs font-medium text-text">Screening Threshold</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setOverrideThreshold(!overrideThreshold)}
                    className="text-[11px] font-semibold text-primary hover:underline"
                  >
                    {overrideThreshold ? "Reset to Baseline" : "Customize"}
                  </button>
                </div>

                {overrideThreshold ? (
                  <div className="mt-2.5 flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted">Sensitivity:</span>
                      <span className="font-mono font-bold text-primary">{customThreshold.toFixed(4)}</span>
                    </div>
                    <input
                      type="range"
                      min="0.2000"
                      max="0.5500"
                      step="0.0050"
                      value={customThreshold}
                      onChange={(e) => setCustomThreshold(parseFloat(e.target.value))}
                      className="w-full accent-primary"
                    />
                    <div className="flex justify-between text-[10px] text-muted">
                      <span>More Sensitive (0.20)</span>
                      <span>Less Sensitive (0.55)</span>
                    </div>
                  </div>
                ) : (
                  <p className="mt-1 text-[11px] text-muted">
                    Using calibrated baseline: <strong className="text-text">{DEFAULT_THRESHOLDS[category]}</strong>{" "}
                    (computed on validation benchmark).
                  </p>
                )}
              </div>

              {/* Action Button */}
              <button
                type="button"
                onClick={runInspection}
                disabled={isLoading || (!selectedFile && !previewUrl)}
                className="mt-1 flex w-full items-center justify-center gap-2 rounded-[var(--radius-control)] bg-primary py-2.5 text-xs font-semibold text-on-primary transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>Running WinCLIP Zero-Shot Inference...</span>
                  </>
                ) : (
                  <>
                    <FileSearch className="size-4" />
                    <span>Run Zero-Shot Quality Inspection</span>
                  </>
                )}
              </button>
            </div>
          </Card>
        </div>

        {/* Right Column: Visual Inspection & Anomaly Heatmap (7 cols) */}
        <div className="flex flex-col gap-5 lg:col-span-7">
          {error && (
            <div className="flex items-start gap-3 rounded-[var(--radius-card)] border border-danger/40 bg-danger/10 p-3 text-xs text-danger">
              <AlertCircle className="size-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Inspection Error:</span> {error}
              </div>
            </div>
          )}

          <Card className="flex flex-col flex-1">
            <CardHeader
              title="Inspection Results & Defect Localization"
              subtitle={
                result
                  ? `Evaluated in ${result.latency_ms.toFixed(1)}ms on ${result.device.toUpperCase()}`
                  : "Awaiting inspection run..."
              }
              aside={
                result && (
                  <div className="flex items-center gap-1 rounded-[var(--radius-control)] border border-border bg-surface-2 p-0.5">
                    <button
                      type="button"
                      onClick={() => setViewMode("side-by-side")}
                      className={cn(
                        "rounded-[var(--radius-control)] px-2 py-1 text-[10px] font-medium transition-colors",
                        viewMode === "side-by-side" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text",
                      )}
                    >
                      Side by Side
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("heatmap")}
                      className={cn(
                        "rounded-[var(--radius-control)] px-2 py-1 text-[10px] font-medium transition-colors",
                        viewMode === "heatmap" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text",
                      )}
                    >
                      Heatmap Only
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("original")}
                      className={cn(
                        "rounded-[var(--radius-control)] px-2 py-1 text-[10px] font-medium transition-colors",
                        viewMode === "original" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text",
                      )}
                    >
                      Original
                    </button>
                  </div>
                )
              }
            />

            {/* Verdict Banner (when inspection finished) */}
            {result && (
              <div
                className={cn(
                  "mb-4 flex items-center justify-between rounded-[var(--radius-control)] border p-3 transition-all",
                  result.is_anomalous
                    ? "border-warn/40 bg-warn/10 text-warn"
                    : "border-ok/40 bg-ok/10 text-ok",
                )}
              >
                <div className="flex items-center gap-2.5">
                  {result.is_anomalous ? (
                    <AlertTriangle className="size-5 shrink-0" />
                  ) : (
                    <CheckCircle2 className="size-5 shrink-0" />
                  )}
                  <div>
                    <div className="font-semibold text-xs tracking-tight">{result.verdict}</div>
                    <div className="text-[11px] opacity-80">
                      Severity: <strong>{result.severity}</strong> &bull; Score:{" "}
                      <strong>{result.anomaly_score.toFixed(4)}</strong> (Threshold: {result.threshold.toFixed(4)})
                    </div>
                  </div>
                </div>
                <Badge tone={result.is_anomalous ? "warn" : "ok"}>
                  {result.is_anomalous ? "QA Review Required" : "Nominal Batch"}
                </Badge>
              </div>
            )}

            {/* Display Viewport */}
            <div className="relative flex-1 min-h-[340px] rounded-[var(--radius-control)] border border-border bg-surface-2 p-2 flex items-center justify-center">
              {isLoading && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-surface/80 backdrop-blur-xs rounded-[var(--radius-control)]">
                  <Loader2 className="size-8 animate-spin text-primary" />
                  <span className="text-xs font-semibold text-text">Computing WinCLIP feature maps...</span>
                  <span className="text-[11px] text-muted">Performing multi-scale window anomaly ensembling</span>
                </div>
              )}

              {heatmapSrc && previewUrl ? (
                <div className="w-full h-full flex flex-col items-center justify-center">
                  {viewMode === "side-by-side" && (
                    <div className="grid w-full grid-cols-2 gap-3">
                      <div className="flex flex-col items-center gap-1.5">
                        <span className="text-[11px] font-medium text-muted">Original Sample</span>
                        <div className="relative aspect-square w-full overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
                          <img
                            src={previewUrl}
                            alt="Original Product"
                            className="size-full object-contain"
                          />
                        </div>
                      </div>

                      <div className="flex flex-col items-center gap-1.5">
                        <span className="text-[11px] font-medium text-muted">Defect Localization (JET Colormap)</span>
                        <div className="relative aspect-square w-full overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
                          <img
                            src={heatmapSrc}
                            alt="Defect Heatmap Overlay"
                            className="size-full object-contain"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {viewMode === "heatmap" && (
                    <div className="relative aspect-square max-h-[380px] w-full overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
                      <img
                        src={heatmapSrc}
                        alt="Defect Heatmap Overlay"
                        className="size-full object-contain"
                      />
                    </div>
                  )}

                  {viewMode === "original" && (
                    <div className="relative aspect-square max-h-[380px] w-full overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
                      <img
                        src={previewUrl}
                        alt="Original Product"
                        className="size-full object-contain"
                      />
                    </div>
                  )}
                </div>
              ) : previewUrl ? (
                <div className="flex flex-col items-center justify-center gap-3">
                  <div className="relative aspect-square max-h-[280px] overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
                    <img src={previewUrl} alt="Preview" className="size-full object-contain" />
                  </div>
                  <span className="text-xs text-muted">
                    Image loaded. Click <strong>&quot;Run Zero-Shot Quality Inspection&quot;</strong> to evaluate.
                  </span>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center gap-2 text-muted">
                  <Eye className="size-8 stroke-1 text-border-strong" />
                  <span className="text-xs">No product image selected yet</span>
                </div>
              )}
            </div>

            {/* Inspection Breakdown Metrics */}
            {result && (
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-2.5">
                  <span className="text-[10px] uppercase font-semibold text-muted">Anomaly Score</span>
                  <div className="mt-0.5 text-base font-mono font-bold text-text">
                    {result.anomaly_score.toFixed(4)}
                  </div>
                  <span className="text-[10px] text-muted">Cosine distance</span>
                </div>

                <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-2.5">
                  <span className="text-[10px] uppercase font-semibold text-muted">Threshold</span>
                  <div className="mt-0.5 text-base font-mono font-bold text-text">
                    {result.threshold.toFixed(4)}
                  </div>
                  <span className="text-[10px] text-muted">
                    {result.anomaly_score >= result.threshold ? "Exceeded" : "Within bounds"}
                  </span>
                </div>

                <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-2.5">
                  <span className="text-[10px] uppercase font-semibold text-muted">Margin</span>
                  <div
                    className={cn(
                      "mt-0.5 text-base font-mono font-bold",
                      result.anomaly_score >= result.threshold ? "text-warn" : "text-ok",
                    )}
                  >
                    {(result.anomaly_score - result.threshold >= 0 ? "+" : "") +
                      (result.anomaly_score - result.threshold).toFixed(4)}
                  </div>
                  <span className="text-[10px] text-muted">Delta vs baseline</span>
                </div>

                <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-2.5">
                  <span className="text-[10px] uppercase font-semibold text-muted">Inference Time</span>
                  <div className="mt-0.5 text-base font-mono font-bold text-text">
                    {result.latency_ms.toFixed(0)} ms
                  </div>
                  <span className="text-[10px] text-muted">Zero-shot CPU</span>
                </div>
              </div>
            )}

            {/* Disclaimer & Regulatory Warning */}
            <CardFooter className="mt-4 text-[11px] text-muted flex items-start gap-2">
              <HelpCircle className="size-3.5 shrink-0 mt-0.5 text-primary" />
              <span>
                <strong>Operational Guidance:</strong> Visual anomaly screening provides automated triage and QA
                prioritization. Pharmaceutical products must undergo certified laboratory QA before lot release.
              </span>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  );
}
