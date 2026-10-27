# Model card: C2 rules baseline (`c2-rules-0.1.0`) and the local-LLM second opinion

Capability: C2 trade-news intelligence. Code: `packages/c2_trade_news`; config `config/c2/`,
`config/priors/disruptions.yaml`. Registered on: 2026-10-27. No learned weights.

## What it is

| Step | Method |
|---|---|
| Text | Title + snippet only (copyright: snippets and links, C2 §11); HTML stripped |
| Places | Gazetteer of the corridor, hubs and chokepoints with aliases (Chittagong/Chattogram/Ctg…), longest match first |
| Type | Regex cues per `DisruptionType`; the earliest cue in the text wins; its span is the evidence |
| Relevance | 0.45 × place weight + 0.35 × type found + 0.2 × logistics topic words; a weak place (country, sea, far hub) also needs a topic word |
| Start, duration, size | Weekday and relative dates resolved from the publish time; "48-hour", "indefinite"; "N vessels", "N TEUs" |
| Status | Resolved / reported cues ("called off", "warn"), else ongoing |
| Events | Same type family at the same place (≤ 150 km, or same country for coarse places) within 72 h; a hazard and the port closures it causes are one event |
| Severity | Type prior × place weight (+0.1 when ≥ 20 vessels are mentioned) |
| Confidence | 1 − Π(1 − reliability × extraction confidence) over distinct outlets; one outlet is capped at 0.5 |
| LLM (top-K) | Local model through Ollama, JSON schema-constrained, temperature 0; every quoted field must be in the text. A "no" scales confidence by 0.6, a grounded "yes" confirms or rescues |

Every field shown in the UI carries a character span into the article text (the grounding rule).

## Evaluation (honest, partial)

| Check | Result | Criterion |
|---|---|---|
| Throughput (rules) | ≈ 3,900 articles/s on one core | C2-AC06: ≥ 5/s |
| JSON validity (LLM) | 12 / 12 parsed under the schema | C2-AC04: 100 % |
| Grounded LLM fields | `llama3.1:8b`: 9 ungrounded fields in 12 answers, 0 positives (it rejected a warehouse fire and a grid failure) | C2-AC04: ≥ 95 % grounded — **not met by llama3.1**; `qwen3:4b` to be compared |
| Unit checks | grounded spans, dates, syndicated copies collapse, hazard + closure = one event, single-source cap | C2-AC05 behaviour |
| Real window (14 days, 5,884 articles) | 16 relevant, 10 events after dedupe; spot check: Red Sea geopolitics still slips in | — |
| **Relevance / type F1 vs a gold set** | **not measured yet**: 150 articles are waiting for human labels (`data/inbox/c2_gold/annotate.csv`, Q-11) | C2-AC01/AC02 |
| Backtest | not run (needs historical GDELT windows) | C2-AC07 |

## Assumptions

Type priors (severity, duration P50/P90, remaining capacity), source reliability, the 0.5
single-source cap and the alert thresholds are estimates in `config/priors/disruptions.yaml`.

## Limits

Title + snippet only; English only (Q-10 default); no GLiNER2 or embeddings yet (A-060); GDELT
rows are titles without snippets; Red Sea geopolitics is over-included; synthetic scenario
articles are processed into scenario-scoped events.
