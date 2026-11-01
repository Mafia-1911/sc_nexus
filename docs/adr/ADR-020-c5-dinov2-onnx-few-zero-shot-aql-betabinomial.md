# ADR-020: C5 on DINOv2-S patches (ONNX, CPU), few- and zero-shot scoring, ISO 2859-1 lots and a beta-binomial lot risk

Status: accepted   Date: 2026-11-01

**Context:** C5 must flag defects on fabric, garment, tablet and capsule images without labelled
defects on day one, decide lots by ISO 2859-1, forecast which lots will fail, and turn a failed
lot into orders at risk with costed options (C5 §2). Inference is CPU only (< 3 s per image,
C5-AC02); heavy models train in notebooks (D-03); MVTec AD is non-commercial (rule 9).

**Decision:**
- **Encoder:** `facebook/dinov2-small` (Apache-2.0) as ONNX from the onnx-community export, run
  with onnxruntime (no PyTorch in the app): 448 px → 32 × 32 patch features in ≈ 0.35 s.
- **Scoring:** AnomalyDINO-style few-shot (nearest patch to k normal references) for the live
  path and the lots; MuSc-style zero-shot mutual scoring within an unlabelled lot as the day-one
  rung. Thresholds at a 5 % FPR on held-out normal images; tiling for large texture images.
- **Gallery precomputed** by `uv run c5 eval` on the host (thumbnails, heatmaps, scores, banks in
  `data/c5/` and `models/c5/`, bind-mounted, never committed); the API serves reads and one live
  few-shot inspection per upload.
- **Lots:** ISO 2859-1 single sampling, normal inspection, level II, from a rule checked cell by
  cell against the ANSI/ASQ Z1.4 tables; the model is assistive (confirmed = flagged ∧
  defective); pharma lots are always held for QA.
- **Risk:** beta-binomial empirical Bayes (industry → plant → line, recency-weighted) with lot
  dispersion; p-chart and EWMA per line. **Impact:** rejected lots → orders at risk → alert with
  rework, replacement, air and buyer-notice options, each with cost and benefit.

**Alternatives considered:** AnomalyCLIP in the app (ViT-L/14@336 CLIP, heavy on CPU; kept as
the offline baseline for C5-AC01); anomalib PatchCore per SKU (needs 100+ normals per SKU, U2
rung); PyTorch in the image (≈ 1 GB larger); a supervised detector on the Roboflow sets (S3 rung,
labels per defect type); a hierarchical PyMC model (notebook; EB is enough at this size).

**Consequences:** + fast, offline, light image, every decision explained (heatmap, counts, AQL
row, costs). − Few-shot needs a handful of normal images per SKU; zero-shot is weaker on
stitching (AUROC 0.71); MVTec images stay off any public deployment (NC); the lot world, defect
rates and costs are synthetic estimates.
