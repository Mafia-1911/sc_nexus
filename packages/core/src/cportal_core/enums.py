"""Shared enums: the single source of truth for every package, the DB and the API (04 §5).

Values are lower-case strings stored as VARCHAR with CHECK constraints (no Postgres ENUM types,
so adding a value is a one-line migration). DisruptionType keeps the brief's upper-case codes
because C2's priors and prompts use them verbatim.
"""

from __future__ import annotations

from enum import StrEnum


class DataMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


class TransportMode(StrEnum):
    SEA = "sea"
    ROAD = "road"
    RAIL = "rail"
    BARGE = "barge"
    AIR = "air"


class CargoProfile(StrEnum):
    DRY_CONTAINER = "dry_container"
    REEFER_2_8C = "reefer_2_8c"
    REEFER_FROZEN = "reefer_frozen"
    DANGEROUS_GOODS = "dangerous_goods"
    BREAKBULK = "breakbulk"


class Industry(StrEnum):
    GARMENTS = "garments"
    PHARMA = "pharma"


class LocationKind(StrEnum):
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    SEAPORT = "seaport"
    RIVER_PORT = "river_port"
    ICD = "icd"
    DEPOT = "depot"
    EPZ = "epz"
    INDUSTRIAL_CLUSTER = "industrial_cluster"
    RAIL_HUB = "rail_hub"
    TOLL_POINT = "toll_point"
    BRIDGE = "bridge"
    WAREHOUSE = "warehouse"
    SITE = "site"
    OTHER = "other"


class PortType(StrEnum):
    SEA = "sea"
    RIVER = "river"
    ICD = "icd"
    DRY = "dry"


class ZoneType(StrEnum):
    PORT_LIMIT = "port_limit"
    ANCHORAGE = "anchorage"
    CHANNEL = "channel"
    BERTH = "berth"
    TERMINAL = "terminal"
    # SC-05: GFW anchorage and dock cells (point/cell geometry, no polygon in OSM).
    ANCHORAGE_CELL = "anchorage_cell"
    DOCK_CELL = "dock_cell"


class OrgKind(StrEnum):
    SUPPLIER = "supplier"
    MANUFACTURER = "manufacturer"
    BUYER = "buyer"
    CARRIER = "carrier"
    LOGISTICS = "3pl"
    PORT_OPERATOR = "port_operator"
    REGULATOR = "regulator"


class FacilityType(StrEnum):
    RAW_MATERIAL_SUPPLIER = "raw_material_supplier"
    SPINNING_MILL = "spinning_mill"
    FABRIC_MILL = "fabric_mill"
    TRIMS_SUPPLIER = "trims_supplier"
    GARMENT_FACTORY = "garment_factory"
    API_MANUFACTURER = "api_manufacturer"
    EXCIPIENT_SUPPLIER = "excipient_supplier"
    PACKAGING_SUPPLIER = "packaging_supplier"
    PHARMA_PLANT = "pharma_plant"
    WAREHOUSE = "warehouse"
    DC = "dc"
    ICD = "icd"
    DEPOT = "depot"
    CUSTOMER_SITE = "customer_site"


class ShipTypeGroup(StrEnum):
    # AIS types 70-79 and GFW "cargo" do not say container vs bulk; `cargo` is that coarse group.
    CARGO = "cargo"
    CONTAINER = "container"
    TANKER = "tanker"
    DRY_BULK = "dry_bulk"
    GENERAL_CARGO = "general_cargo"
    RO_RO = "ro_ro"
    PASSENGER = "passenger"
    FISHING = "fishing"
    TUG_SERVICE = "tug_service"
    OTHER = "other"


class PortCallStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class PortCallMethod(StrEnum):
    GFW = "gfw"
    AIS_STATE_MACHINE = "ais_state_machine"
    CPA_REPORT = "cpa_report"  # DS-PORT-07 berthing report (day precision)
    SIM = "sim"


class VisitKind(StrEnum):
    """SC-03: most Chattogram cargo visits never reach a dock (lighterage at anchor)."""

    BERTH_CALL = "berth_call"
    ANCHORAGE_ONLY = "anchorage_only"


class PortCallFlag(StrEnum):
    """SC-04: standard quality flags on port calls."""

    LONG_STAY = "long_stay"  # > 60 days
    WINDOW_OVERLAP = "window_overlap"
    LOW_CONFIDENCE = "low_confidence"
    DATE_PRECISION_DAY = "date_precision_day"
    CENSORED = "censored"


class SatelliteSensor(StrEnum):
    S1 = "s1"
    S2 = "s2"
    GFW_SAR = "gfw_sar"


class WeatherKind(StrEnum):
    FORECAST = "forecast"
    ARCHIVE = "archive"
    MARINE_FORECAST = "marine_forecast"
    MARINE_ARCHIVE = "marine_archive"


class HolidayKind(StrEnum):
    """SC-12: the `holidays` package misses extended Eid closures and truck bans."""

    PUBLIC = "public"
    EXTENDED_CLOSURE = "extended_closure"
    TRUCK_BAN = "truck_ban"


class TradeFlowDirection(StrEnum):
    IMPORT = "import"
    EXPORT = "export"


class DiscoveredVia(StrEnum):
    """SC-10: how an article reached us."""

    GDELT_GKG = "gdelt_gkg"
    GDELT_DOC = "gdelt_doc"
    RSS = "rss"
    RELIEFWEB = "reliefweb"
    MANUAL = "manual"


class DisruptionType(StrEnum):
    PORT_CONGESTION = "PORT_CONGESTION"
    PORT_OPERATIONS_SUSPENDED = "PORT_OPERATIONS_SUSPENDED"
    LABOR_STRIKE_BLOCKADE = "LABOR_STRIKE_BLOCKADE"
    CYCLONE_STORM = "CYCLONE_STORM"
    FLOOD = "FLOOD"
    EARTHQUAKE_OTHER_NATURAL = "EARTHQUAKE_OTHER_NATURAL"
    FIRE_EXPLOSION = "FIRE_EXPLOSION"
    CHOKEPOINT_DISRUPTION = "CHOKEPOINT_DISRUPTION"
    SECURITY_CONFLICT_PIRACY = "SECURITY_CONFLICT_PIRACY"
    CUSTOMS_SYSTEM_REGULATORY = "CUSTOMS_SYSTEM_REGULATORY"
    TRADE_POLICY_SANCTION = "TRADE_POLICY_SANCTION"
    ENERGY_UTILITY_SHORTAGE = "ENERGY_UTILITY_SHORTAGE"
    CYBER_INCIDENT = "CYBER_INCIDENT"
    CARRIER_CAPACITY_RATES = "CARRIER_CAPACITY_RATES"
    INLAND_TRANSPORT_DISRUPTION = "INLAND_TRANSPORT_DISRUPTION"
    PHARMA_REGULATORY_QUALITY = "PHARMA_REGULATORY_QUALITY"
    SUPPLIER_INCIDENT = "SUPPLIER_INCIDENT"
    DEMAND_SHOCK = "DEMAND_SHOCK"
    OTHER = "OTHER"


class EventStatus(StrEnum):
    REPORTED = "reported"
    CONFIRMED = "confirmed"
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    RETRACTED = "retracted"


class AlertLevel(StrEnum):
    """SC-09: GDACS-style alert levels, reused for any hazard source."""

    GREEN = "green"
    ORANGE = "orange"
    RED = "red"


class LinkMethod(StrEnum):
    ALIAS = "alias"
    FUZZY = "fuzzy"
    EMBEDDING = "embedding"
    GEO_BUFFER = "geo_buffer"
    MANUAL = "manual"


class ShipmentStatus(StrEnum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    AT_PORT = "at_port"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class TransportEventType(StrEnum):
    """DCSA Track & Trace event types."""

    TRANSPORT = "TRANSPORT"
    EQUIPMENT = "EQUIPMENT"
    SHIPMENT = "SHIPMENT"


class EventClassifier(StrEnum):
    """DCSA classifiers: planned, estimated, actual."""

    PLN = "PLN"
    EST = "EST"
    ACT = "ACT"


class OrderStatus(StrEnum):
    OPEN = "open"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    LATE = "late"
    CANCELLED = "cancelled"


class BatchStatus(StrEnum):
    IN_PROCESS = "in_process"
    QUARANTINE = "quarantine"
    RELEASED = "released"
    REJECTED = "rejected"
    REWORK = "rework"


class ImageSplit(StrEnum):
    TRAIN = "train"
    VALID = "valid"
    TEST = "test"
    GROUND_TRUTH = "ground_truth"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACK = "ack"
    SNOOZED = "snoozed"
    CLOSED = "closed"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationAction(StrEnum):
    INCREASE_SAFETY_STOCK = "increase_safety_stock"
    PULL_FORWARD_PO = "pull_forward_po"
    DUAL_SOURCE = "dual_source"
    REROUTE = "reroute"
    MODE_SHIFT = "mode_shift"
    EXPEDITE_AIR = "expedite_air"
    REINSPECT = "reinspect"
    HOLD_SHIPMENT = "hold_shipment"
    NOTIFY_CUSTOMER = "notify_customer"


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class Capability(StrEnum):
    C1 = "c1"
    C2 = "c2"
    C3 = "c3"
    C4 = "c4"
    C5 = "c5"
    NEXUS = "nexus"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
