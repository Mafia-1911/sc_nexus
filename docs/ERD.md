# Entity-relationship diagram (domain model v1)

_Generated from `packages/core/src/cportal_core/models/` (51 tables) by `make erd`. Edit the models, not this file._

Every domain table also carries the lineage columns (04 §4, SC-01): `source_id`, `source_record_id`, `data_mode`, `is_synthetic`, `scenario_id`, `generator_version`, `ingested_at`, `available_at`, `created_at`, `updated_at`. The database enforces `is_synthetic = (data_mode = 'synthetic')` and that synthetic rows carry a `scenario_id`. `outbox_event` and `job` are infrastructure without lineage.

## Reference and supply network

```mermaid
erDiagram
  bom_edge {
    uuid id PK
    uuid parent_product_id FK
    uuid component_product_id FK
    double qty_per_unit
  }
  country_indicator {
    uuid id PK
    string country_iso3
    string indicator_code
    string indicator_name
    integer year
    double value
    string unit
  }
  emission_factor {
    uuid id PK
    string mode
    string vehicle_class
    string fuel
    string unit
    string ghg_unit
    double value
    string scope
    integer year
  }
  external_id {
    uuid id PK
    string entity_type
    uuid entity_id
    string scheme
    string value
    date valid_from
    date valid_to
  }
  facility {
    uuid id PK
    uuid organization_id FK
    string name
    string name_key
    string facility_type
    uuid location_id FK
    string cluster
    jsonb capacity
    jsonb certifications
  }
  fx_rate {
    uuid id PK
    date date
    string base
    string quote
    double rate
  }
  holiday {
    uuid id PK
    date date
    string kind
    string name
    string country_iso2
    string notice_url
  }
  lane {
    uuid id PK
    uuid origin_location_id FK
    uuid dest_location_id FK
    string mode
    jsonb via
    double distance_km
    double typical_transit_d
    geometry geom
  }
  location {
    uuid id PK
    string locode
    integer geonames_id
    string name
    string name_bn
    string country_iso2
    string kind
    string cluster
    geometry geom
    geometry geom_area
    jsonb attrs
  }
  organization {
    uuid id PK
    string name
    string name_key
    string country_iso2
    string kind
    string industry
    string lei
    string osh_id
    string wikidata_qid
    boolean is_fictional
    vector name_embedding
    jsonb attrs
  }
  port {
    uuid id PK
    uuid location_id FK
    string locode
    string name
    string port_type
    string operator
    double max_draught_m
    double max_loa_m
    boolean tidal
    jsonb berths_count_by_class
  }
  port_zone {
    uuid id PK
    uuid port_id FK
    string zone_type
    string name
    string cell_id
    geometry geom
    date valid_from
    date valid_to
    jsonb attrs
  }
  product {
    uuid id PK
    string sku
    string name
    string industry
    string hs6
    string gtin
    string uom
    double unit_value_usd
    boolean cold_chain
    jsonb temp_range_c
    integer shelf_life_days
    boolean hazardous
  }
  supply_edge {
    uuid id PK
    uuid from_facility_id FK
    uuid to_facility_id FK
    uuid product_id FK
    double share
    double capacity_per_week
    double lead_time_mean_d
    double lead_time_sd_d
    string mode
    uuid lane_id FK
    double cost_per_unit_usd
    boolean is_inferred
    double confidence
    date valid_from
    date valid_to
  }
  trade_flow {
    uuid id PK
    string reporter_iso3
    string partner_iso3
    string hs_code
    integer year
    string flow
    double value_usd
    double net_wgt_kg
    boolean is_mirror
  }
  product ||--o{ bom_edge : "component_product_id"
  product ||--o{ bom_edge : "parent_product_id"
  location ||--o{ facility : "location_id"
  organization ||--o{ facility : "organization_id"
  location ||--o{ lane : "origin_location_id"
  location ||--o{ lane : "dest_location_id"
  location ||--o{ port : "location_id"
  port ||--o{ port_zone : "port_id"
  lane |o--o{ supply_edge : "lane_id"
  facility ||--o{ supply_edge : "to_facility_id"
  product ||--o{ supply_edge : "product_id"
  facility ||--o{ supply_edge : "from_facility_id"
```

## Maritime and port

```mermaid
erDiagram
  ais_position_latest {
    uuid id PK
    uuid vessel_id FK
    biginteger mmsi
    datetime ts
    datetime received_at
    string msg_type
    geometry geom
    double sog_kn
    double cog_deg
    double heading_deg
    smallinteger nav_status
    double draught_m
    string destination
    datetime eta_reported
  }
  port_activity_daily {
    uuid id PK
    uuid port_id FK
    date date
    integer calls_total
    jsonb calls_by_type
    double import_t
    double export_t
    jsonb trade_by_type
  }
  port_call {
    uuid id PK
    uuid vessel_id FK
    uuid port_id FK
    string status
    string visit_kind
    datetime arrival_ts
    datetime anchorage_start_ts
    datetime anchorage_end_ts
    datetime berth_start_ts
    datetime berth_end_ts
    datetime departure_ts
    datetime departure_planned_ts
    double waiting_h
    double berth_h
    double dwell_h
    uuid berth_zone_id FK
    boolean censored
    string method
    smallinteger confidence
    string gfw_visit_id
    jsonb quality_flags
  }
  port_call_stop {
    uuid id PK
    uuid port_call_id FK
    integer seq
    string cell_id
    uuid zone_id FK
    boolean at_dock
    geometry geom
    datetime start_ts
    datetime end_ts
  }
  port_state_snapshot {
    uuid id PK
    uuid port_id FK
    datetime ts
    jsonb queue_by_type
    jsonb berth_occupancy
    integer arrivals_24h
    integer departures_24h
    double mean_wait_h_24h
    jsonb weather
    jsonb tide
    integer sar_count
    double sar_age_h
  }
  satellite_observation {
    uuid id PK
    string sensor
    string scene_id
    datetime acq_ts
    string area_name
    uuid zone_id FK
    geometry footprint
    string asset_href
    double cloud_pct
    integer detections_count
    jsonb detections
  }
  vessel {
    uuid id PK
    string imo
    biginteger mmsi
    string name
    string call_sign
    smallinteger ship_type_ais
    string ship_type_group
    double loa_m
    double beam_m
    double dwt
    double gt
    string flag_iso3
  }
  vessel_identity {
    uuid id PK
    uuid vessel_id FK
    biginteger mmsi
    string name
    string call_sign
    string flag_iso3
    datetime valid_from
    datetime valid_to
  }
  weather_observation {
    uuid id PK
    string point_name
    uuid location_id FK
    geometry geom
    datetime ts
    string kind
    datetime issued_at
    double temperature_2m_c
    double precipitation_mm
    double wind_speed_10m_kmh
    double wind_gusts_10m_kmh
    double wind_direction_10m_deg
    double pressure_msl_hpa
    double wave_height_m
    double wave_period_s
    double swell_wave_height_m
    double sea_level_height_msl_m
    double ocean_current_velocity_kmh
  }
  zone_presence_daily {
    uuid id PK
    uuid zone_id FK
    string area_name
    date date
    uuid vessel_id FK
    biginteger mmsi
    string imo
    string ship_type_group
    double hours
    double mean_sog_kn
    datetime entry_ts
    datetime exit_ts
  }
  vessel |o--o{ ais_position_latest : "vessel_id"
  port_activity_daily }o--|| port : "port_id"
  port_call }o--|o port_zone : "berth_zone_id"
  vessel ||--o{ port_call : "vessel_id"
  port_call }o--|| port : "port_id"
  port_call ||--o{ port_call_stop : "port_call_id"
  port_call_stop }o--|o port_zone : "zone_id"
  port_state_snapshot }o--|| port : "port_id"
  satellite_observation }o--|o port_zone : "zone_id"
  vessel ||--o{ vessel_identity : "vessel_id"
  weather_observation }o--|o location : "location_id"
  zone_presence_daily }o--|o port_zone : "zone_id"
  vessel |o--o{ zone_presence_daily : "vessel_id"
```

## News and disruption events

```mermaid
erDiagram
  article {
    uuid id PK
    string url
    string url_canonical
    string source_name
    datetime published_at
    string lang
    string source_lang
    text title
    string snippet
    string content_hash
    string discovered_via
    string feed_id
    jsonb gdelt_ids
    jsonb themes
    jsonb locations
    double tone
    vector embedding
  }
  disruption_event {
    uuid id PK
    string type
    string subtype
    text title
    text summary
    string status
    double severity
    double confidence
    string alert_level
    datetime start_est
    double start_uncertainty_h
    datetime end_est
    double duration_p50_h
    double duration_p90_h
    geometry geom
    array locodes
    array country_iso3
    datetime first_seen
    datetime last_updated
    string cluster_key
    jsonb external_ids
    string url
  }
  event_entity_link {
    uuid id PK
    uuid event_id FK
    string entity_type
    uuid entity_id
    string link_method
    double link_confidence
    jsonb impact_hint
  }
  event_mention {
    uuid id PK
    uuid event_id FK
    uuid article_id FK
    jsonb extracted
    jsonb evidence_spans
    string extractor_version
    double extraction_confidence
  }
  disruption_event ||--o{ event_entity_link : "event_id"
  article ||--o{ event_mention : "article_id"
  disruption_event ||--o{ event_mention : "event_id"
```

## Orders, shipments and routes

```mermaid
erDiagram
  customer_order {
    uuid id PK
    string reference
    uuid buyer_org_id FK
    uuid product_id FK
    uuid facility_id FK
    double qty
    date due_date
    string incoterm
    integer priority
    string status
    double revenue_usd
  }
  inventory_position {
    uuid id PK
    uuid facility_id FK
    uuid product_id FK
    datetime ts
    double on_hand
    double on_order
    double allocated
    double safety_stock
    double reorder_point
    double days_of_cover
  }
  route_option {
    uuid id PK
    uuid request_id FK
    jsonb legs
    geometry geom
    double time_p50_h
    double time_p90_h
    double cost_bdt
    double cost_usd
    double co2e_kg
    double on_time_prob
    integer pareto_rank
    text explanation
  }
  route_request {
    uuid id PK
    uuid origin_location_id FK
    uuid dest_location_id FK
    string cargo_profile
    datetime deadline
    jsonb constraints
    jsonb weights
  }
  shipment {
    uuid id PK
    string reference
    jsonb mode_chain
    uuid origin_location_id FK
    uuid dest_location_id FK
    jsonb containers
    string cargo_profile
    datetime planned_eta
    datetime predicted_eta_p50
    datetime predicted_eta_p90
    string status
  }
  shipment_leg {
    uuid id PK
    uuid shipment_id FK
    integer seq
    string mode
    uuid from_location_id FK
    uuid to_location_id FK
    uuid vessel_id FK
    datetime planned_dep
    datetime planned_arr
    datetime actual_dep
    datetime actual_arr
    uuid route_option_id FK
  }
  shipment_order {
    uuid id PK
    uuid shipment_id FK
    uuid order_id FK
    double qty
  }
  transport_event {
    uuid id PK
    uuid shipment_id FK
    string event_type
    string classifier
    string event_code
    uuid location_id FK
    datetime event_ts
    uuid vessel_id FK
    string equipment_reference
  }
  customer_order }o--|o facility : "facility_id"
  customer_order }o--|| organization : "buyer_org_id"
  customer_order }o--|| product : "product_id"
  inventory_position }o--|| facility : "facility_id"
  inventory_position }o--|| product : "product_id"
  route_request ||--o{ route_option : "request_id"
  route_request }o--|| location : "origin_location_id"
  route_request }o--|| location : "dest_location_id"
  shipment }o--|| location : "dest_location_id"
  shipment }o--|| location : "origin_location_id"
  shipment_leg }o--|| location : "to_location_id"
  shipment_leg }o--|| location : "from_location_id"
  shipment_leg }o--|o vessel : "vessel_id"
  shipment ||--o{ shipment_leg : "shipment_id"
  route_option |o--o{ shipment_leg : "route_option_id"
  shipment ||--o{ shipment_order : "shipment_id"
  customer_order ||--o{ shipment_order : "order_id"
  shipment ||--o{ transport_event : "shipment_id"
  transport_event }o--|o location : "location_id"
  transport_event }o--|o vessel : "vessel_id"
```

## Quality

```mermaid
erDiagram
  batch {
    uuid id PK
    string lot_code
    uuid product_id FK
    uuid facility_id FK
    uuid supplier_facility_id FK
    string line
    string shift
    integer size_units
    datetime produced_at
    string status
    string aql_level
    jsonb aql_result
  }
  image_dataset {
    uuid id PK
    string dataset_ref
    string title
    string licence
    boolean nc
    string url
    string task
    jsonb categories
    jsonb classes
    integer n_images
    jsonb splits
    biginteger size_bytes
  }
  inspection_image {
    uuid id PK
    uuid dataset_id FK
    uuid batch_id FK
    uuid product_id FK
    string category
    string split
    string label
    string uri
    string mask_uri
    integer width
    integer height
    datetime captured_at
    string source_dataset
  }
  inspection_result {
    uuid id PK
    uuid image_id FK
    uuid model_version_id FK
    double image_score
    boolean is_anomalous
    double threshold
    string defect_type
    string severity
    string heatmap_uri
    string mask_uri
    double latency_ms
  }
  batch }o--|| product : "product_id"
  batch }o--|| facility : "facility_id"
  batch }o--|o facility : "supplier_facility_id"
  inspection_image }o--|o product : "product_id"
  batch |o--o{ inspection_image : "batch_id"
  image_dataset |o--o{ inspection_image : "dataset_id"
  inspection_image ||--o{ inspection_result : "image_id"
  inspection_result }o--|o model_version : "model_version_id"
```

## Platform: scenarios, alerts, models, sources, jobs

```mermaid
erDiagram
  alert {
    uuid id PK
    string kind
    string severity
    text title
    text body
    jsonb entity_refs
    uuid event_id FK
    string status
    string dedupe_key
  }
  data_source {
    uuid id PK
    string ds_id
    string name
    string tier
    string status
    string default_mode
    string fallback
    text licence
    boolean nc
    string cadence
    datetime last_success_ts
  }
  ingestion_run {
    uuid id PK
    datetime started_at
    datetime ended_at
    string status
    integer records
    integer errors
    double latency_ms
    jsonb notes
  }
  job {
    uuid id PK
    string kind
    jsonb params
    string status
    double progress
    jsonb result
    text error
    datetime started_at
    datetime finished_at
  }
  model_version {
    uuid id PK
    string capability
    string name
    string version
    string artifact_uri
    jsonb card
    jsonb metrics
    string licence
    datetime registered_at
    boolean is_active
  }
  outbox_event {
    uuid id PK
    string topic
    jsonb payload
    datetime processed_at
    integer attempts
    text last_error
  }
  prediction {
    uuid id PK
    string capability
    string target_type
    uuid target_id
    datetime as_of
    double horizon_h
    double value
    jsonb quantiles
    jsonb dist_params
    uuid model_version_id FK
    jsonb explanation
    string features_hash
  }
  recommendation {
    uuid id PK
    uuid alert_id FK
    string action_type
    jsonb target_refs
    jsonb params
    double expected_benefit_usd
    double expected_cost_usd
    double confidence
    text rationale
    jsonb evidence_refs
    string status
    datetime decided_at
    text feedback
  }
  scenario {
    uuid id PK
    string key
    string name
    jsonb definition
    integer seed
    boolean is_baseline
    string created_by
  }
  scenario_result {
    uuid id PK
    uuid run_scenario_id FK
    string capability
    jsonb kpis
    jsonb artifacts
  }
  alert }o--|o disruption_event : "event_id"
  model_version |o--o{ prediction : "model_version_id"
  alert ||--o{ recommendation : "alert_id"
  scenario ||--o{ scenario_result : "run_scenario_id"
```
