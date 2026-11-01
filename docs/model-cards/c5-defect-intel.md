# Model card: C5 defect intelligence (`c5-baseline-0.1.0`)

Capability: C5 defect intelligence. Code: `packages/c5_defect_intel`. Registered on: 2026-11-01
(`model_version` rows `c5-* (<category>)` and `c5-lot-risk-betabinomial` per scenario). Design:
ADR-020. Raw reports: `c5-eval.json` (`uv run c5 eval`).
Licences: encoder `facebook/dinov2-small` Apache-2.0 (ONNX export by onnx-community); images
**MVTec AD CC BY-NC-SA 4.0 (non-commercial)** and StitchNet v2 CC BY 4.0. Images and heatmaps
stay in `data/` (never committed, C5-AC07).

## What it is

| Part | Method | Output |
|---|---|---|
| Encoder | DINOv2-S, ONNX on onnxruntime (CPU), 448 px → 32 × 32 patch features (14 px) | L2-normalised patch vectors |
| Z0 zero-shot | MuSc-style mutual scoring (ICLR'24) within the unlabelled lot: a patch's score is the mean of its lowest 30 % nearest-patch distances to up to 32 other images. Our variant: DINOv2-S, one layer, no RsCIN | image score, heatmap |
| F1 few-shot | AnomalyDINO-style (WACV'25): cosine distance to the nearest patch of k normal references (k = 1, 4, 8) | image score, heatmap |
| Threshold | 95th percentile of 30 held-out normal images (target FPR 5 %) | per category |
| Lots | ISO 2859-1 single sampling, normal, level II (garments AQL 2.5 major; pharma 1.0); confirmed defects = flagged items an inspector confirms; pharma always held for QA | decision, evidence |
| Lot risk | Beta-binomial empirical Bayes (industry → plant → line, 14-day half-life) with lot dispersion κ | P(next lot fails AQL) |
| SPC | p-chart (3σ per sample size) and EWMA (λ 0.3) per line | alarms |
| Impact | Failed lot → its order → rework, replacement, air, buyer notice, each with cost and benefit (estimates in `config/priors/c5.yaml`) | alert + recommendations |

Image score = mean of the top 1 % patch scores. The deployed method per category is the better
image AUROC of zero-shot and few-shot (k = 8); the live upload path is always few-shot (k = 8).

## Evaluation: images (C5-AC01, AC02, AC03)

| Category (data, licence) | Method | Image AUROC | Pixel AUROC | Recall @ thr. | FPR on test normals | ms / image |
|---|---|---|---|---|---|---|
| stitch (StitchNet v2 (Roboflow), CC BY 4.0) | zero-shot (MuSc-style) | 0.715 | — | 0.49 | 0.23 | 485 |
| stitch (StitchNet v2 (Roboflow), CC BY 4.0) | few-shot k = 1 | 0.806 | — | 0.69 | 0.27 | 384 |
| stitch (StitchNet v2 (Roboflow), CC BY 4.0) | few-shot k = 4 | 0.884 | — | 0.79 | 0.21 | 392 |
| stitch (StitchNet v2 (Roboflow), CC BY 4.0) | few-shot k = 8 **(deployed)** | 0.892 | — | 0.77 | 0.14 | 424 |
| pill (MVTec AD pill, CC BY-NC-SA 4.0) | zero-shot (MuSc-style) | 0.951 | 0.962 | 0.83 | 0.08 | 485 |
| pill (MVTec AD pill, CC BY-NC-SA 4.0) | few-shot k = 1 | 0.916 | 0.947 | 0.62 | 0.08 | 397 |
| pill (MVTec AD pill, CC BY-NC-SA 4.0) | few-shot k = 4 | 0.947 | 0.955 | 0.65 | 0.04 | 405 |
| pill (MVTec AD pill, CC BY-NC-SA 4.0) | few-shot k = 8 **(deployed)** | 0.967 | 0.961 | 0.67 | 0.04 | 424 |
| capsule (MVTec AD capsule, CC BY-NC-SA 4.0) | zero-shot (MuSc-style) | 0.930 | 0.984 | 0.67 | 0.09 | 498 |
| capsule (MVTec AD capsule, CC BY-NC-SA 4.0) | few-shot k = 1 | 0.947 | 0.980 | 0.73 | 0.04 | 402 |
| capsule (MVTec AD capsule, CC BY-NC-SA 4.0) | few-shot k = 4 | 0.947 | 0.984 | 0.80 | 0.04 | 412 |
| capsule (MVTec AD capsule, CC BY-NC-SA 4.0) | few-shot k = 8 **(deployed)** | 0.960 | 0.986 | 0.89 | 0.09 | 424 |
| carpet (MVTec AD carpet, CC BY-NC-SA 4.0) | zero-shot (MuSc-style) | 0.998 | 0.989 | 1.00 | 0.21 | 585 |
| carpet (MVTec AD carpet, CC BY-NC-SA 4.0) | few-shot k = 1 | 1.000 | 0.990 | 1.00 | 0.29 | 407 |
| carpet (MVTec AD carpet, CC BY-NC-SA 4.0) | few-shot k = 4 | 1.000 | 0.991 | 1.00 | 0.29 | 415 |
| carpet (MVTec AD carpet, CC BY-NC-SA 4.0) | few-shot k = 8 **(deployed)** | 1.000 | 0.991 | 1.00 | 0.25 | 432 |
| leather (MVTec AD leather, CC BY-NC-SA 4.0) | zero-shot (MuSc-style) **(deployed)** | 1.000 | 0.993 | 0.96 | 0.00 | 1,426* |
| leather (MVTec AD leather, CC BY-NC-SA 4.0) | few-shot k = 1 | 1.000 | 0.990 | 1.00 | 0.00 | 910* |
| leather (MVTec AD leather, CC BY-NC-SA 4.0) | few-shot k = 4 | 1.000 | 0.990 | 1.00 | 0.22 | 922* |
| leather (MVTec AD leather, CC BY-NC-SA 4.0) | few-shot k = 8 | 1.000 | 0.990 | 1.00 | 0.16 | 1,037* |

Split per category: stitch 8 refs / 30 calibration / 439 test; pill 8 refs / 30 calibration / 167 test; capsule 8 refs / 30 calibration / 132 test; carpet 8 / 30 / 117 (28 normal); leather 8 / 30 / 124 (32 normal). Carpet and leather are scored as whole images (1024 px → 448 px, untiled, A-091).
\* Leather was timed while the Docker stack was starting on the same CPU (encode 892 ms vs ≈ 400 ms for the other categories); the slowdown is contention, not the method.

ms / image is encoding plus scoring on this laptop's CPU (4 threads): every category is far
below the 3 s budget (C5-AC02); the live upload measured 0.5 s through the API. Few-shot gains
from k = 1 to k = 8 on every object category (stitch 0.81 → 0.89, pill 0.92 → 0.97, capsule
0.95 → 0.96; C5-AC03); the textures are already at 1.000 with k = 1, so there is nothing to gain. The zero-shot rung needs no references at all and is already strong on
tablets and capsules (0.93–0.95) but weak on stitching (0.71), where a handful of normal images
of the SKU is worth asking for.

The textures (carpet, leather) are nearly solved for ranking: image AUROC 0.998–1.000 and pixel
AUROC ≈ 0.99 with every method, in line with published AnomalyDINO and MuSc results on MVTec
textures. Their weak point is the threshold, not the score: MVTec's `test/good` images score
higher than the `train/good` images used for calibration, so carpet at k = 8 flags 25 % of
test normals (7 of 28) at a threshold set for 5 %. Leather ties at AUROC 1.000, so the rule
deploys zero-shot, which has 0 % FPR and 96 % recall.

**Not met yet (honest):** AnomalyCLIP, the brief's named baseline, has not been run yet. The
user runs it (U-05): the script, setup and split manifest are in
`packages/c5_defect_intel/baselines/` and `data/cache/aclip/`; results go to
`c5-eval-anomalyclip.json` and then into this table. VisA `capsules` waits for the optional
download (U-04). The thresholds come from only 30 normal images, so the realised FPR on test
normals is often above 5 % (stitch 14 %, capsule 9 %, carpet 25 %, leather few-shot 16–22 %);
calibrating on a few of the plant's own recent normals is the fix.

## Evaluation: lots, risk and impact (synthetic world, C5-AC04…AC06)

Baseline scenario, world 0.3.0: 1,021 finished-goods lots on 46 lines over 60 days.

| Check | Result | Criterion |
|---|---|---|
| ISO 2859-1 plans | Table 1 and Table 2-A, every cell for AQL 0.65–6.5 matches ANSI/ASQ Z1.4 (parsed from CRAN AQLSchemes, not typed); the brief's example (lot 3,201–10,000 → L, n 200, Ac 10) | C5-AC04 — **met** |
| Lot decisions vs the OC curve | simulated acceptance within ±3 points of the binomial OC at 1–10 % defect rates (`test_lot_decisions_follow_the_oc_curve`) | C5-AC04 — **met** |
| Garment lots | 559 accepted, 68 rejected (10.8 %) at AQL 2.5 on confirmed defects | — |
| Pharma lots | 394 held for QA review (never automatic); none exceeded its AQL limit | C5 §6 pharma rule |
| Model recall inside lots | 76 % of the truly defective sampled items were flagged | — |
| **Escapes** (assistive cost) | 8.1 % of garment lots were accepted although perfect detection would have failed them | reported honestly |
| Lot risk, last 20 days (327 lots, 21 failures) | Brier 0.046 vs 0.057 for the base rate (−20 %); reliability: predicted 0.04 / observed 0.03 (n 302), 0.29 / 0.27 (n 11); sparse above 0.4 | C5-AC05 — **met** (calibrated where the data are) |
| Impact | 15 failed lots in the last 14 days → 15 alerts, 32 options (rework and replacement always; air and buyer notice for the order at risk); every option has cost and benefit | C5-AC06 — **met** |

The escape rate is the number to watch: it falls as recall rises (more references per SKU,
the U2 rung), and it is why the model directs inspectors rather than replacing them.

## Limits

- MVTec and StitchNet are not Bangladeshi garment or pharma line images: the domain gap is
  real; few-shot banks from a plant's own normal images are the intended fix.
- Lots, lines, defect rates, orders and costs are synthetic estimates (fictional plants with
  guarded names, Q-05); every inspected item is a real dataset image with its provenance.
- The model is assistive: it directs inspectors; it never releases or rejects pharma lots.
