from pydantic import BaseModel
from typing import Optional


# --- Enrichment request/response models (called by n8n Workflow 1) ---

class EnrichDomainRequest(BaseModel):
    domain: str

class EnrichDomainResponse(BaseModel):
    domain: str
    tld: str
    length: int
    digit_count: int
    period_count: int
    entropy: float
    is_nxdomain: bool
    active_period_days: int
    a_count: int
    aaaa_count: int
    mx_count: int
    ns_count: int
    soa_count: int
    txt_count: int
    cname_count: int
    ptr_count: int
    srv_count: int
    # ASN info (from first resolved IP)
    country: str
    asn: str
    asn_description: str


class EnrichIPRequest(BaseModel):
    ip: str

class EnrichIPResponse(BaseModel):
    ip: str
    country: str
    asn: str
    asn_description: str


class EnrichURLRequest(BaseModel):
    url: str

class EnrichURLResponse(BaseModel):
    url: str
    extracted_domain: str
    path: str
    tld: str
    length: int
    digit_count: int
    special_char_count: int
    path_depth: int
    has_query: bool
    has_fragment: bool
    entropy: float
    file_extension: str
    http_status: Optional[int] = None
    content_type: str
    server: str
    head_failed: bool
    resolved_ip: Optional[str] = None


# --- Attribution request/response models (called by n8n Workflow 2) ---

class TrainRequest(BaseModel):
    k_folds: Optional[int] = None
    ae_epochs: Optional[int] = None
    gnn_epochs: Optional[int] = None

class TrainResponse(BaseModel):
    status: str
    message: str = ""
    metrics: dict = {}


class PredictRequest(BaseModel):
    alpha_gnn: Optional[float] = 0.6
    alpha_lp: Optional[float] = 0.4
    event_ids: Optional[list[str]] = None
    include_labeled: bool = False

class PredictionResult(BaseModel):
    event_id: str
    predicted_apt: str
    confidence: float
    method: str = "gnn+lp"

class PredictResponse(BaseModel):
    status: str
    predictions: list[PredictionResult]


class LPRequest(BaseModel):
    iterations: Optional[int] = None

class LPResponse(BaseModel):
    status: str
    predictions: list[PredictionResult]
    iterations: int


class StoreResultsRequest(BaseModel):
    predictions: list[PredictionResult]


class StatusResponse(BaseModel):
    service_status: str
    neo4j_connected: bool
    model_trained: bool
    last_training: Optional[str] = None
    graph_stats: dict
    events_per_apt: dict


# --- Tiered attribution (Unit 42-inspired) ---

class TierPrediction(BaseModel):
    prediction: str
    confidence: float
    assessment: str            # "high_confidence", "moderate_confidence", "low_confidence"

class TieredAttribution(BaseModel):
    tier3_named_actor: TierPrediction
    tier2_nation_state: TierPrediction
    tier1_activity_cluster: TierPrediction
    recommended_tier: int      # 1, 2, or 3
    summary: str               # human-readable summary

class PredictResponse(BaseModel):
    status: str
    predictions: list[PredictionResult]


# --- Ad-hoc attribution (submit unknown IOCs) ---

class AttributeIOC(BaseModel):
    type: str          # "domain", "ip", or "url"
    value: str         # e.g. "suspicious.example.com"

class AttributeRequest(BaseModel):
    iocs: list[AttributeIOC]

class AttributeResponse(BaseModel):
    status: str
    predicted_apt: str
    confidence: float
    scores: dict               # per-APT probability breakdown
    iocs_processed: int
    event_id: str              # temp event ID (for reference)
    tiered: Optional[TieredAttribution] = None
