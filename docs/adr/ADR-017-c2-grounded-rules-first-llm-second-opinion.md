# ADR-017: C2 as grounded rules first, a local LLM as a second opinion, Nexus for buffers

Status: accepted   Date: 2026-10-27

**Context:** C2 must turn news into grounded, deduplicated events on a CPU laptop with ≈ 7 GB
RAM, next to Docker. The brief's stack is GLiNER2 for every article and a small local LLM for
the top-K (Q-03). A test of the pulled `llama3.1:8b` took ≈ 100 s to load and ≈ 15 s per
article, and rejected every candidate with mostly ungrounded quotes.

**Decision:**
- **Baseline:** a gazetteer + regex lexicon with character spans for every field (always on,
  ≈ 4k articles/s). It is the baseline any learned extractor must beat.
- **LLM:** `cportal_core.llm.OllamaProvider` (ADR-008) with JSON-schema constrained decoding;
  verdicts are grounded, stored as `prediction` rows and merged as a **second opinion**: a "no"
  lowers confidence, a grounded "yes" confirms or rescues. It runs from the host (`uv run c2
  llm`); the Docker worker skips it unless Ollama is reachable.
- **Events:** deterministic clustering by type family, place and a 72 h window; real articles
  give real events, each scenario's synthetic articles give that scenario's events.
- **Links:** LOCODEs on events feed C1's gateway directly; area events (flood, strike, power)
  link to the scenario's facilities in the named cluster as synthetic links.
- **Buffers in Nexus:** `packages/nexus` (may import capability services) turns each open
  alert into a C1 what-if and a safety-stock recommendation (08 §4); C1 and C2 stay
  independent (import-linter).

**Alternatives considered:** GLiNER2 now (adds PyTorch, ~1 GB+, model download; deferred to
"deepen C2"); LLM verdicts as overrides (an 8B model vetoed true positives); embeddings for
clustering (not needed at tens of events a day).

**Consequences:** + fast, explainable, every highlight is in the text; works offline. − Recall
is limited to the lexicon; precision on geopolitics is weak; F1 waits for the gold set (Q-11).
