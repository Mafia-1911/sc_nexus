# ADR-005: CPU inference; training in free notebooks

Status: accepted   Date: 2026-10-26

**Context:** D-03 (Colab/Kaggle training, CPU-only app) and the CPU budgets in 02 §11.

**Decision:** Models export to ONNX (OpenVINO for vision) or LightGBM/joblib; the app loads them
lazily on CPU and falls back to the package baseline (`model: "baseline"`) when an artifact is
missing. `model_version` and model cards record data hashes, metrics and licences.

**Alternatives considered:** GPU serving (not available on the demo laptop); hosted inference
(paid, D-07).

**Consequences:** + offline demo. − Model size is bounded by CPU latency; measured per capability.
