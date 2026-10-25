# C2 · Trade-news intelligence

**TL;DR.** Ingest international and Bangladeshi news plus hazard and regulatory feeds. Turn them into **grounded, deduplicated disruption events** (type, location, affected entities, start and expected duration, severity, confidence), each backed by quoted evidence. Link events to the C1 graph, raise alerts, and recommend **inventory-buffer adjustments**. The CPU-first stack: rules + **GLiNER2** (schema-driven extraction on CPU) for every article, with a small local LLM and **grammar-constrained JSON** only for the top-K relevant articles. A bigger open model runs in a Kaggle notebook to create silver labels. Real data from day one (GDELT and RSS are free); synthetic data only in tests. Build order: 2 of 5.

## 1. Job to be done

- **C2-R01** I get early alerts about disruptions that affect my lanes, ports, suppliers or products (strikes and blockades, cyclones, port suspension or congestion, customs outages, rail shortages, Red Sea, export bans, FDA actions), each with a confidence score and the evidence behind it.
- **C2-R02** I see **who and what is affected** (graph links), **when** it starts, how long it lasts (P50/P90) and **how severe** it is.
- **C2-R03** I get a buffer recommendation: units and days of cover per product and facility, with cost and expected value.
- **C2-R04** Duplicate reports of the same story collapse into one event, and the event's lifecycle (reported → confirmed → ongoing → resolved) updates over time.

## 2. Hackathon scope

- **Must:** GDELT DOC + RSS + GDACS + openFDA ingest; dedupe; rules and GLiNER2 triage and extraction; geocoding with a Bangladesh gazetteer; entity linking; clustering into events; severity and confidence; alerts; buffer recommendation; the Radar UI; a gold set of ~300 articles; one backtest.
- **Should:** small local LLM extraction for the top-K (per Q-03); news-as-sensor extraction of numbers (vessels waiting, containers in yard) for C4; ReliefWeb.
- **Stretch:** Bangla news translation; GLiNER2 fine-tune on silver labels; ACLED; event knowledge-graph timeline.

## 3. Inputs

DS-NEWS-01/02 (GDELT), DS-NEWS-03 (RSS), DS-WX-02 (GDACS), DS-NEWS-04 (ReliefWeb), DS-PHARMA-01/03 (openFDA, FDA pages), DS-NEWS-06 (GSCPI context), DS-GEO-04 (gazetteers), the C1 entities (link targets), and C4 port state (corroboration via NX).

**GDELT query seeds** (iterate in M0; GDELT supports OR groups and `sourcecountry`, `domain` and `theme` filters):

- Location set: `(Chittagong OR Chattogram OR Mongla OR Payra OR Pangaon OR Kamalapur OR "Bay of Bengal")`
- Topic set: `(port OR vessel OR container OR shipping OR congestion OR strike OR blockade OR customs OR cyclone OR flood OR shutdown)`
- Industry sets: `(garment OR RMG OR apparel OR textile OR knitwear)` · `(pharmaceutical OR "active pharmaceutical ingredient" OR API OR "drug shortage")`
- Global lanes: `("Red Sea" OR Suez OR "Bab el-Mandeb" OR Houthi OR Malacca OR Colombo OR Singapore) AND (shipping OR container)`

## 4. Output contract

The tables are `article`, `disruption_event`, `event_mention` (with `evidence_spans`), `event_entity_link`, `alert` and `recommendation` (`04-domain-model.md` §3). The extraction schema (the JSON the extractors must return, validated by Pydantic):

```json
{
  "is_supply_chain_disruption": true,
  "event_type": "LABOR_STRIKE_BLOCKADE",
  "summary": "Port workers' strike halts container handling at Chattogram",
  "locations": [{"text": "Chattogram port", "locode": "BDCGP"}],
  "entities": [{"text": "Chittagong Port Authority", "type": "port_authority"}],
  "commodities": [{"text": "readymade garments", "hs_hint": "61"}],
  "start": {"text": "from Sunday", "iso": "2026-11-01", "confidence": 0.7},
  "duration": {"text": "indefinite", "p50_h": null},
  "magnitude": [{"text": "40 vessels waiting at outer anchorage", "metric": "vessels_waiting", "value": 40}],
  "status": "ongoing",
  "evidence": {"event_type": [120, 188], "start": [190, 203]}
}
```

**Grounding rule:** every non-null field needs an evidence span that exists in the text. Fields without one are dropped and counted as `ungrounded`.

## 5. Method ladder (pipeline)

1. **Ingest and normalise:** canonical URL, content hash, MinHash-LSH near-duplicate detection (datasketch), main-text extraction (trafilatura) only where the ToS allows (otherwise title and snippet), language ID, and storage per the copyright rule (`03-data-sources.md` §5).
2. **Triage (cheap first):** (a) keyword, theme and source priors give a relevance prior; (b) **GLiNER2** classification (relevant? which `DisruptionType`?) on CPU; (c) a zero-shot NLI baseline (DeBERTa-v3 zero-shot) as a sanity comparison.
3. **Extraction:** **GLiNER2** schema extraction for entities (port, chokepoint, company, vessel, commodity, location, date expression, duration, quantity), relations and structured fields. For the **top-K** relevant articles (budgeted, e.g. ≤ 200/day on CPU), a **small local LLM** (Q-03; e.g. Qwen3.5-4B / Qwen3-4B-Instruct or Gemma 4 E4B, 4-bit GGUF via llama.cpp/Ollama) fills the JSON schema with **constrained decoding** (llama.cpp GBNF, Ollama `format` JSON schema, Outlines or XGrammar). Ungrounded fields are rejected.
4. **Normalisation:** dates with `dateparser` relative to the publish time (ranges and relative expressions); geocoding with the Bangladesh gazetteer (UN/LOCODE + GeoNames + a curated list of EPZs, ICDs, districts and spellings such as Chittagong/Chattogram/Ctg), falling back to Nominatim (cached, ≤ 1 request/s); entity linking through the alias table, then rapidfuzz, then multilingual embeddings (bge-m3 or multilingual-e5) in pgvector. Below threshold, a link goes to a review queue.
5. **Event clustering:** incremental clustering on (type, location within R km, a time window, summary embedding similarity) into canonical `disruption_event`s, with lifecycle updates and source diversity counted.
6. **Severity and confidence:** severity = f(type prior, magnitude cues, scope = number of linked critical nodes, duration). Confidence = f(independent sources × reliability, extraction confidence, NX physical corroboration). Priors live in `config/priors/disruptions.yaml`, covering duration and lead-time impact per type and region.
7. **Impact and recommendations:** linked nodes and lanes feed C1 exposure, then the lead-time delta distribution, then the **buffer recommendation** (safety-stock maths in `08-nexus-layer.md` §4, with pharma shelf-life and cold-storage constraints and garment season deadlines). Alert if severity ≥ θ and the event touches a critical node; dedupe and rate-limit alerts.
8. **News as sensor (Should):** extract numeric congestion indicators ("N vessels waiting at outer anchorage", "N TEUs in yard") into `port_state_snapshot` with `source=news`. These are weak labels and features for C4.

## 6. Models and libraries

| Role | Default (CPU) | Notes |
|---|---|---|
| NER + classification + structured extraction | **GLiNER2** (`fastino/gliner2-base-v1` or `-large-v1`; base ~205M params; verify the names) | One forward pass on CPU; schema-driven |
| Generative extraction (top-K) | Small local LLM, 4-bit (Q-03) | Grammar-constrained JSON; temperature 0 |
| Silver labels / distillation | A larger open model in a **Kaggle notebook** (e.g. a 14B–32B-class Qwen or gpt-oss-20b; verify fit on T4×2) | Creates the training/eval set; never runs in the app |
| Embeddings | bge-m3 or multilingual-e5-base | Bangla-capable; dedupe, linking, clustering |
| Zero-shot baseline | `MoritzLaurer/deberta-v3-large-zeroshot-v2.0` (or base for CPU) | Honesty check for triage |
| Bangla (stretch) | BanglaBERT (csebuetnlp) for classification; OPUS-MT bn→en or NLLB-200-distilled-600M (**CC BY-NC**) for translation | Prefer English editions first (Q-10) |
| Tooling | trafilatura, datasketch, dateparser, rapidfuzz, Label Studio or Argilla (annotation) | — |

## 7. Evaluation and acceptance

**Gold set:** ~300 articles (≥ 100 about Bangladesh). Pre-annotate them with the notebook LLM, then have a human correct them (Q-11). Freeze the set in `data/samples/c2_gold/`.

| ID | Criterion (on the gold set unless noted) |
|---|---|
| C2-AC01 | Relevance F1 ≥ 0.80; report the zero-shot NLI baseline alongside |
| C2-AC02 | Event-type macro-F1 ≥ 0.70 on the top 8 types |
| C2-AC03 | Entity/location F1 ≥ 0.70; geocoding within 25 km ≥ 0.85; auto-link precision ≥ 0.90 |
| C2-AC04 | JSON validity 100 % (constrained decoding); grounded fields ≥ 95 % |
| C2-AC05 | Near-duplicates collapse: ≥ 90 % of the syndicated copies in the gold set join the same event |
| C2-AC06 | Throughput: ≥ 5 articles/s through triage and GLiNER2 on 4 vCPU; LLM top-K jobs don't block the API |
| C2-AC07 | **Backtest** on ≥ 1 historical window (`08-nexus-layer.md` §6): report alert lead time (K-03) and precision (K-04), including misses |
| C2-AC08 | Buffer recommendations show units, days of cover, cost, expected value, confidence and evidence links |

## 8. API

`GET /events?type=&status=&since=&bbox=&min_conf=` · `GET /events/{id}` (with mentions and evidence) · `POST /events/{id}/feedback` · `GET /alerts?status=open` · `POST /alerts/{id}/ack` · `GET /recommendations?kind=buffer` · `POST /recommendations/{id}/decision`

## 9. UI

The Disruption Radar page: the event feed (type icon, severity bar, confidence, source count, *corroborated by* chips), a map of event footprints, a timeline, and an event drawer with evidence quotes (highlighted spans with links out), linked entities (jump to C1) and the recommendation card. A filter row sits above the feed (type, region, confidence, industry). A backtest banner appears when the app is time-travelling.

## 10. Integration hooks

C1 (links, then exposure) · C4 (event features, news-as-sensor, corroboration) · C3 (closures and constraints: a road or bridge closure, port suspension or Eid ban becomes a routing constraint) · NX (fusion, recommendations, scenarios, daily brief).

## 11. Risks and guardrails

- **Hallucinations:** grounding spans plus constrained decoding; never show ungrounded fields.
- **Copyright:** snippets and links only.
- **Name ambiguity:** "Chittagong" vs "Chattogram" vs "Ctg"; API (pharma) vs API (software). Keep a disambiguation list in the gazetteer.
- **Single-source rumours:** confidence capped at 0.5 without corroboration.
- **Source bias:** report coverage by source.
- **Rate limits:** GDELT is strict, so use a token bucket and caching.
- Open questions: Q-03, Q-10, Q-11.
