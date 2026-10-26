# ADR-008: LLM provider interface: local only

Status: accepted   Date: 2026-10-26

**Context:** Q-03 answered (a): local LLM only; GLiNER2 first. Settings already expose
`LLM_BASE_URL` and `LLM_MODEL` (default an OpenAI-compatible Ollama endpoint).

**Decision:** C2 calls an `LLMProvider` protocol with one implementation for any OpenAI-compatible
local server, grammar-constrained JSON output, timeouts and a cache. GLiNER2 handles triage and
entity extraction for every article; the LLM runs only on the top-K as a worker job. The model
is chosen at M4 from small instruct models that fit the laptop (≈ 7 GB RAM: a 3–4B model at
4-bit), with the choice and its benchmark in this ADR's successor.

**Alternatives considered:** hosted free tiers (excluded by Q-03); no LLM (loses extraction
quality on long articles).

**Consequences:** + offline and free. − Needs Ollama (or llama.cpp) installed before M4; memory is
tight next to Postgres and the web app.
