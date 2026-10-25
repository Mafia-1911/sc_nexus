# 04 · Domain model, IDs, persistence, events, API conventions

**TL;DR.** One shared vocabulary serves all five capabilities. Entities use open standard identifiers wherever they exist: UN/LOCODE, IMO/MMSI, HS, GTIN, LEI, Open Supply Hub ID, GeoNames. Shipment events follow the **DCSA Track & Trace** event model; product and lot events follow **GS1 EPCIS 2.0** concepts. Every table carries lineage columns. This file is a **draft**: M0 probe evidence may change it (record each change in an ADR), and M1 freezes v1.

## 1. Identifier standards

| Thing | Primary ID | Also store | Notes |
|---|---|---|---|
| Port, ICD, city | **UN/LOCODE** (e.g. BDCGP) | GeoNames ID, WPI number | Internal surrogate `location_id` (UUID); LOCODE is unique where present |
| Vessel | **IMO** (when known) | MMSI, call sign, name history | MMSI can change and be reused. Link through `vessel_identity` with validity intervals. MID 405 = Bangladesh flag |
| Company / organisation | Internal UUID | LEI (GLEIF), Open Supply Hub ID, Wikidata QID | `is_fictional` flag (mandatory) |
| Facility | Internal UUID | OSH ID; geocode; cluster tag (e.g. `gazipur`, `cepz`) | Type enum (below) |
| Product | Internal SKU | **HS 6-digit** code (HS 2022), GTIN (pharma) | `industry` = garments or pharma |
| Container / transport document | ISO 6346 container number (synthetic: valid check digit) | Carrier booking/BL reference | Synthetic numbers must not collide with real owners. Pick an owner code you have checked is unregistered in the BIC registry, and always set `is_synthetic` |
| Location (generic) | Internal UUID | WGS84 point (SRID 4326); optional polygon | Geometry is PostGIS `geography` for distance work, `geometry` for spatial ops |

## 2. Core entities

```
Organization 1─* Facility *─* Product (via Produces / Stores)
Facility ─SupplyEdge(product, share, capacity, lead_time, mode, is_inferred)→ Facility
Product ─BomEdge(qty_per_unit)→ Product
Port 1─* PortZone (port_limit | anchorage | channel | berth | terminal)
Vessel 1─* PortCall *─1 Port ;  PortCall 1─* PortCallSegment (anchorage|transit|berth|shift)
Shipment 1─* ShipmentLeg ; Shipment 1─* TransportEvent (DCSA) ; Shipment *─* Order
Batch(lot) *─1 Facility ; Batch 1─* InspectionResult ; Batch ─allocated_to→ Order
Article *─* DisruptionEvent (via EventMention w/ evidence spans) ; DisruptionEvent *─* (Port|Facility|Organization|Product|Lane) via EventEntityLink
Scenario 1─* ScenarioResult (per capability)
ModelVersion 1─* Prediction ; Alert ─has→ Recommendation(s)
DataSource 1─* IngestionRun
```

## 3. Table sketch (v0, refined in M1)

Every table also has the **lineage columns** in §4.

| Table | Key columns (beyond id) | Owner |
|---|---|---|
| `location` | locode, geonames_id, name, name_bn, country_iso2, kind, geom (point), geom_area (polygon, nullable) | core |
| `port` | location_id, locode, port_type (sea/river/ICD/dry), operator, max_draught_m, max_loa_m, tidal (bool), berths_count_by_class (jsonb) | core |
| `port_zone` | port_id, zone_type (port_limit, anchorage, channel, berth, terminal), name, geom (polygon), source | core / C4 |
| `organization` | name, country_iso2, lei, osh_id, wikidata_qid, kind (supplier, manufacturer, buyer, carrier, 3PL), is_fictional | core |
| `facility` | organization_id, facility_type (raw_material_supplier, spinning_mill, fabric_mill, trims_supplier, garment_factory, api_manufacturer, excipient_supplier, packaging_supplier, pharma_plant, warehouse, dc, icd, depot, customer_site), location_id, cluster, capacity (jsonb), certifications (jsonb) | core / C1 |
| `product` | sku, name, industry, hs6, gtin, uom, unit_value_usd, cold_chain (bool), temp_range_c, shelf_life_days, hazardous (bool) | core |
| `bom_edge` | parent_product_id, component_product_id, qty_per_unit | core / C1 |
| `supply_edge` | from_facility_id, to_facility_id, product_id, share (0–1), capacity_per_week, lead_time_mean_d, lead_time_sd_d, mode, lane_id, cost_per_unit_usd, is_inferred, confidence, valid_from, valid_to | C1 |
| `lane` | origin_location_id, dest_location_id, mode (sea, road, rail, barge, air), via (jsonb list of LOCODEs), typical_transit_d | core / C3 |
| `vessel` | imo, mmsi, name, ship_type_ais, ship_type_group, loa_m, beam_m, dwt, gt, flag | C4 |
| `ais_position_latest` | vessel_id/mmsi, ts, geom, sog_kn, cog_deg, heading_deg, nav_status, draught_m, destination, eta_reported | C4 (history in Parquet) |
| `port_call` | vessel_id, port_id, status (active, completed), arrival_ts, anchorage_start_ts, anchorage_end_ts, berth_start_ts, berth_end_ts, departure_ts, waiting_h, berth_h, dwell_h, berth_zone_id, censored (bool), method (gfw, ais_state_machine, sim), quality_flags (jsonb) | C4 |
| `port_state_snapshot` | port_id, ts, queue_by_type (jsonb), berth_occupancy (jsonb), arrivals_24h, departures_24h, mean_wait_h_24h, weather (jsonb), tide (jsonb), sar_count, sar_age_h | C4 |
| `satellite_observation` | sensor (S1, S2), scene_id, acq_ts, footprint (polygon), asset_href, cloud_pct, detections_count, detections (jsonb) | C4 |
| `shipment` | reference, mode_chain, origin_location_id, dest_location_id, containers (jsonb), cargo_profile (dry, reefer, dg), planned_eta, predicted_eta_p50, predicted_eta_p90, status | NX |
| `shipment_leg` | shipment_id, seq, mode, from_location_id, to_location_id, vessel_id (nullable), planned_dep, planned_arr, actual_dep, actual_arr, route_option_id (nullable) | NX / C3 |
| `transport_event` | shipment_id, event_type (TRANSPORT, EQUIPMENT, SHIPMENT), classifier (PLN, EST, ACT), event_code (ARRI, DEPA, LOAD, DISC, GTIN, GTOT…), location_id, event_ts, vessel_id | NX (DCSA-aligned) |
| `customer_order` | buyer_org_id, product_id, qty, due_date, incoterm, priority, status, revenue_usd | core |
| `inventory_position` | facility_id, product_id, ts, on_hand, on_order, allocated, safety_stock, reorder_point, days_of_cover | core / NX |
| `batch` | product_id, facility_id, line, shift, size_units, produced_at, status (in_process, quarantine, released, rejected, rework), aql_level, aql_result (jsonb) | C5 |
| `inspection_image` | batch_id, product_id, category, uri, width, height, captured_at, source_dataset (provenance) | C5 |
| `inspection_result` | image_id, model_version_id, image_score, is_anomalous, threshold, defect_type (nullable), severity, heatmap_uri, mask_uri, latency_ms | C5 |
| `article` | url, url_canonical, source_name, published_at, lang, title, snippet, content_hash, gdelt_ids (jsonb), themes (jsonb) | C2 |
| `disruption_event` | type, subtype, title, summary, status (reported, confirmed, ongoing, resolved, retracted), severity (0–1), confidence (0–1), start_est, start_uncertainty_h, end_est, duration_p50_h, duration_p90_h, geom (multipoint/polygon), locodes (text[]), first_seen, last_updated, cluster_key | C2 |
| `event_mention` | event_id, article_id, extracted (jsonb), evidence_spans (jsonb: field → [start, end, quote]), extractor_version, extraction_confidence | C2 |
| `event_entity_link` | event_id, entity_type, entity_id, link_method (alias, fuzzy, embedding, geo-buffer, manual), link_confidence, impact_hint | C2 / C1 |
| `route_request` / `route_option` | request: origin, dest, cargo_profile, deadline, constraints, weights. Option: legs (jsonb), geom (multiline), time_p50_h, time_p90_h, cost_bdt, cost_usd, co2e_kg, on_time_prob, pareto_rank, explanation | C3 |
| `scenario` / `scenario_result` | definition (jsonb), seed, created_by; result: capability, kpis (jsonb), artifacts (jsonb) | NX |
| `alert` | kind, severity_label, title, body, entity_refs (jsonb), event_id (nullable), status (open, ack, snoozed, closed), dedupe_key | NX |
| `recommendation` | alert_id, action_type (increase_safety_stock, pull_forward_po, dual_source, reroute, mode_shift, expedite_air, reinspect, hold_shipment, notify_customer), target_refs, params (jsonb), expected_benefit_usd, expected_cost_usd, confidence, rationale, evidence_refs, status (proposed, accepted, dismissed), decided_at, feedback | NX |
| `model_version` | capability, name, version, artifact_uri, card (jsonb), metrics (jsonb), licence, registered_at, is_active | core |
| `prediction` | capability, target_type, target_id, as_of, horizon_h, value, quantiles (jsonb: p10/p50/p90), dist_params (jsonb), model_version_id, explanation (jsonb), features_hash | core |
| `data_source` / `ingestion_run` | DS-ID, mode, status, last_success_ts, cadence; run: started, ended, records, errors, latency_ms, notes | core |
| `outbox_event` | topic, payload (jsonb), created_at, processed_at, attempts | core |

**Indexes:** GiST on every `geom`; B-tree on `(target_type, target_id, as_of)` for predictions; `(port_id, ts)` for snapshots; HNSW (pgvector) on any embedding columns (`article.embedding`, `organization.name_embedding`).

## 4. Lineage, time and units (every table)

- **Lineage:** `source_id` (DS-ID or `sim`), `source_record_id`, `mode` (live, replay, synthetic), `is_synthetic` (bool), `scenario_id` (nullable), `generator_version` (nullable), `ingested_at`, `created_at`, `updated_at`.
- **Temporal validity**, where facts change: `valid_from` and `valid_to` (on supply_edge, vessel_identity, port_zone).
- **Time:** `timestamptz` in UTC; display in Asia/Dhaka (UTC+6, no DST). Never store local time without its zone.
- **Units:** use suffixes in column names (`_h`, `_d`, `_km`, `_kn`, `_m`, `_t`, `_teu`, `_kg`, `_co2e_kg`, `_usd`, `_bdt`). Money always records its currency; FX rates go in a table with date and source.

## 5. Shared enums (single source of truth in `packages/core/enums.py`)

- **DisruptionType** (shared with C2; priors in `config/priors/disruptions.yaml`): `PORT_CONGESTION, PORT_OPERATIONS_SUSPENDED, LABOR_STRIKE_BLOCKADE, CYCLONE_STORM, FLOOD, EARTHQUAKE_OTHER_NATURAL, FIRE_EXPLOSION, CHOKEPOINT_DISRUPTION, SECURITY_CONFLICT_PIRACY, CUSTOMS_SYSTEM_REGULATORY, TRADE_POLICY_SANCTION, ENERGY_UTILITY_SHORTAGE, CYBER_INCIDENT, CARRIER_CAPACITY_RATES, INLAND_TRANSPORT_DISRUPTION, PHARMA_REGULATORY_QUALITY, SUPPLIER_INCIDENT, DEMAND_SHOCK, OTHER`
- **Mode:** `SEA, ROAD, RAIL, BARGE, AIR`
- **CargoProfile:** `DRY_CONTAINER, REEFER_2_8C, REEFER_FROZEN, DANGEROUS_GOODS, BREAKBULK`
- **DataMode:** `LIVE, REPLAY, SYNTHETIC`

## 6. Internal event topics (outbox)

| Topic | Emitted by | Typical consumers |
|---|---|---|
| `source.ingested` | connectors | feature refresh, freshness KPI |
| `ais.positions_batch` | AIS collector | port-call state machine (C4), live map |
| `port_call.updated` / `port_call.closed` | C4 | predictions refresh, shipment ETA (NX), label store |
| `port_state.updated` | C4 | C4 forecasts, fusion (NX) |
| `disruption.created` / `.updated` / `.resolved` | C2 | C1 impact, NX recommendations, C3 constraints, C4 features, alerts |
| `prediction.created` | any capability | NX tracking, alerts |
| `inspection.completed` / `batch.status_changed` | C5 | NX impact, C1 supplier quality score |
| `scenario.run_requested` / `.completed` | NX | all capabilities / UI |
| `alert.raised` / `recommendation.decided` | NX | UI push, feedback store |

The payload carries only IDs plus a small summary. Consumers re-read the authoritative rows. Handlers are idempotent.

## 7. API conventions (`/api/v1`)

- REST + JSON. Geometries are **GeoJSON** (RFC 7946). Times are ISO-8601 with a `Z` suffix. Pagination uses a cursor (`?cursor=&limit=`). Errors use `application/problem+json`.
- Every response that carries data includes `meta: {mode, sources: [DS-IDs], as_of, model_version?}`. The UI renders the badge from it.
- Read endpoints never trigger heavy compute. Expensive work goes through `POST …/jobs`, which returns `202 + job_id`. Clients poll `GET /jobs/{id}` or listen on the WebSocket.
- Resource groups: `/graph`, `/events`, `/alerts`, `/recommendations`, `/routes`, `/ports`, `/vessels`, `/shipments`, `/quality`, `/scenarios`, `/sources`, `/models`, `/jobs`, `/ws/live`.
- The OpenAPI spec is the contract. CI generates `apps/web/lib/api/types.ts` with `openapi-typescript` and fails on drift.
