# C5 · Manufacturing defect intelligence

**TL;DR.** Inspect product images for anomalies **without labelled defects on day one**: use zero-shot anomaly detection (**AnomalyCLIP** as the named baseline, plus at least one newer method), then move up a **cold-start ladder** (few-shot, then unsupervised, then supervised) as normal and defect images accumulate. Aggregate items into **lots**, apply **AQL sampling decisions** (ISO 2859-1), forecast **defective-batch risk**, and turn defects into **inventory and delivery-commitment impact** (orders at risk, then replan via C3, then supplier quality score in C1). Images come from real public datasets mapped to fictional SKUs; batches and orders are synthetic. Inference runs on CPU (precompute the demo gallery). Pharma batch release always stays with a human. Build order: 5 of 5.

## 1. Job to be done

- **C5-R01** As a garment QA manager, I upload or stream fabric and garment images and get anomaly heatmaps, so inspectors look where it matters, plus lot-level AQL decisions.
- **C5-R02** As a pharma QA lead, I get tablet, capsule and blister screening support and drift alarms per line. The system recommends; humans release.
- **C5-R03** As a planner, I see which orders and deliveries a defective batch puts at risk, and the options (rework, replace, expedite).
- **C5-R04** A supplier's or plant's quality history feeds its C1 risk score.

## 2. Hackathon scope

- **Must:** an evaluation notebook comparing ≥ 2 zero-shot methods on the target categories; CPU-exported inference behind `/quality/inspections`; tiling for fabric; threshold calibration; AQL lot logic; the batch board; orders-at-risk impact; the Quality Lab UI with heatmaps.
- **Should:** few-shot mode (k = 1–8 normal images per SKU) with AnomalyDINO; SPC drift alarms; a defect-rate forecast; a "camera simulator" stream.
- **Stretch:** full unsupervised models (anomalib PatchCore/EfficientAD) per SKU; a supervised defect-type detector (YOLO-seg/RT-DETR on the Roboflow sets); VLM text explanations; an active-learning queue.

## 3. Inputs

DS-VIS-01 (MVTec AD `pill`, `capsule`, `carpet`, `leather`, plus others as auxiliary data), DS-VIS-02 (VisA `capsules` etc.), DS-VIS-03 (LOCO, packaging logic), DS-VIS-04 (fabric and stitching sets), DS-VIS-05 (tablet sets). From `sim`: products, lines, shifts, batches, allocations to orders, production schedule. Each image keeps its `source_dataset` provenance and licence.

## 4. Output contract

`inspection_image`, `inspection_result` (score, threshold, flag, heatmap/mask URIs, latency, model version), `batch` (AQL result JSON: lot size, code letter, sample size, Ac/Re, defects found, decision), plus predictions (`target_type=batch`, P(fail)) and `recommendation` rows (rework, reinspect, expedite_air, notify_customer). Events: `inspection.completed`, `batch.status_changed`.

## 5. Method ladder (the cold-start ladder per category or SKU)

| Rung | When | Method (reuse) | CPU notes |
|---|---|---|---|
| Z0 zero-shot | Day 1, no images of this SKU | **AnomalyCLIP** (ICLR'24; object-agnostic prompts) as the named baseline, plus ≥ 1 of: **AA-CLIP** (CVPR'25), **FB-CLIP** (CVPR'26; code and MVTec/VisA weights; AnomalyCLIP data setup), **VisualAD** (CVPR'26; language-free; CLIP or DINOv2 backbones; reports ~99 % fewer *learnable* parameters, while compute is still dominated by the backbone), **RareCLIP** (ICCV'25; online; ~59 ms reported), **MuSc** (ICLR'24; training-free, scores a **batch** of unlabelled images, which fits lot-level screening). Follow the **cross-dataset protocol**: models trained on VisA are evaluated on MVTec and vice versa; never test on training data | ViT-L/14@336 CLIP models are heavy on CPU. Prefer VisualAD/DINOv2-S variants for live use and precompute the heavy models for the gallery |
| F1 few-shot | 1–16 normal images uploaded | **AnomalyDINO** (WACV'25; DINOv2 patch kNN) or WinCLIP+ | DINOv2-S is CPU-friendly |
| U2 unsupervised | ≥ 100–200 normals per SKU | **anomalib**: PatchCore, EfficientAD (plus newer models the installed version ships); export to OpenVINO/ONNX | Fast on CPU |
| S3 supervised | Labelled defects accumulate | YOLO-seg / RT-DETR for defect **types** (stain, hole, broken stitch; chip, crack, discolouration, empty blister pocket) | Optional |
| Explain (stretch) | Any | Small VLM caption of the anomaly crop ("stain near seam, ~4 mm") as an **assistive** note | Precompute |

**Tiling and thresholds:** split fabric images into overlapping tiles (e.g. 512 px with 64 px overlap) and take the max-pool tile score. Choose the per-category threshold on held-out normal images for a target FPR (e.g. 5 %), store it in the model card, and report recall at that FPR.

## 6. From items to lots, forecasts and impact

1. **AQL (ISO 2859-1, single sampling, normal inspection, general level II):** map lot size to a code letter, then to a sample size and Ac/Re. Example: lot 3,201–10,000 gives letter L and n = 200; at AQL 2.5 that is Ac 10 / Re 11. **Implement from a verified table**, with unit tests on the published values. Garment defaults: AQL 2.5 for major and 4.0 for minor defects (configurable per buyer).
2. **Pharma rule:** the output is a "QA review required" packet (evidence, heatmaps, statistics), **never** an automatic release or reject.
3. **Defective-batch forecast:** a hierarchical beta-binomial model (line ⊂ plant ⊂ supplier; empirical Bayes on CPU, or PyMC/NumPyro in a notebook), with optional LightGBM on process covariates (shift, machine, material lot or supplier, humidity). The output is P(next batch fails AQL). **SPC:** p-chart plus EWMA/CUSUM drift alarms per line.
4. **Impact:** a failed or held batch reduces available-to-promise (ATP) and starts a re-allocation. Open orders whose due date falls before the replacement or rework completes are **at risk** (units, value, buyer). Recommendations include rework or reinspect, replacement production, **expedite** (C3 air vs sea option with cost and CO2e) and notifying the customer. The supplier or plant quality score updates in C1.

## 7. Evaluation and acceptance

| ID | Criterion |
|---|---|
| C5-AC01 | The notebook reports image AUROC, pixel AUROC/AUPRO and recall@5 %FPR per category for ≥ 2 zero-shot methods (AnomalyCLIP + ≥ 1 newer) on MVTec `pill`/`capsule`/`carpet`/`leather`, VisA `capsules` and ≥ 1 fabric dataset, under the cross-dataset protocol |
| C5-AC02 | The chosen live model meets **< 3 s per image** on 4 vCPU (measured), or the gallery is precomputed and the live path uses a lighter model |
| C5-AC03 | Few-shot (if built): AUROC at k = 1, 4, 8 is reported against zero-shot on the same categories |
| C5-AC04 | AQL logic matches the standard's published values in unit tests; lot decisions on simulated lots match the operating-characteristic expectations |
| C5-AC05 | The defect-risk forecast is calibrated (Brier score and reliability vs a naive base rate) |
| C5-AC06 | Each failed batch in the demo produces orders-at-risk and ≥ 2 recommendations, each with cost and benefit |
| C5-AC07 | Licences are tracked: NC datasets are flagged, and the repo has only download scripts plus small samples that the licences allow |

## 8. API

`POST /quality/inspections` (multipart: image, batch_id, category; returns score, flag, heatmap URL; async for batches) · `GET /quality/inspections/{id}` · `GET /quality/batches?status=` · `GET /quality/batches/{id}` (AQL, items, forecast, impact) · `GET /quality/lines/{id}/spc` · `POST /quality/fewshot/{sku}` (upload normal images)

## 9. UI

The Quality Lab page: upload or stream controls, an image grid with heatmap overlays (opacity slider) and masks, the batch board (AQL status pills with icon and label), SPC charts per line, the defect-risk forecast, and the impact panel (orders, inventory, delivery commitments) with **Replan** (opens C3 prefilled) and **Notify** actions. Each model card is linked (method, data, threshold, licence).

## 10. Integration hooks

C1 (quality feature, plant node status), C3 (expedite routing), NX (recommendations, scenario "batch rejected", door-ETA impact), C2 (FDA recalls and warning letters as external quality events for pharma suppliers).

## 11. Risks and guardrails

- **Domain gap:** MVTec is not real garment-line imagery. Say so, and offer few-shot adaptation.
- **Textured fabric false positives:** tiling plus calibration.
- **Regulatory claims:** assistive only for pharma; no automatic release.
- **NC licences:** keep within hackathon use (Q-06).
- **Image provenance:** keep the source dataset on every image.
- Open questions: Q-16.
