# ADR-014: Name packs and the brand variable

Status: accepted   Date: 2026-10-26

**Context:** Q-05: real, well-known Bangladeshi company names may appear in the demo as names only;
AGENTS.md rule 3 forbids attaching synthetic risk or defects to real firms. Q-07: the product
name must be a variable.

**Decision:** The database stores only fictional names plus a stable `name_key`. A name pack
(`CPORTAL_NAME_PACK`: `fictional` by default, `bd_demo` with cited real names for the hero
manufacturers) swaps display names at read time. Views that show adverse synthetic attributes
(defects, recalls, supplier failures, risk scores) request the guarded name and get the
fictional one unless the pack sets `allow_adverse: true`. The UI shows the pack's banner when
real names are active. The brand comes from `CPORTAL_BRAND_NAME` ("Supply Chain Nexus").

**Alternatives considered:** writing real names into synthetic rows (risk of fabricated negative
claims about real firms); fictional names only (the user's demo wish).

**Consequences:** + switching packs needs no re-seed; + the guardrail is tested in the API. − Text
fields in synthetic events never contain real names (contract-tested), so news-style text
stays generic.
