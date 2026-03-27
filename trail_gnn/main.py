"""
TRAIL GNN FastAPI service.

Provides:
- IOC enrichment endpoints (called by n8n Workflow 1)
- GNN training/inference endpoints (called by n8n Workflow 2)
"""

import os
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks

from . import config
from .neo4j_client import Neo4jClient
from .enrichment import enrich_domain, enrich_ip, enrich_url
from .schemas import (
    EnrichDomainRequest, EnrichDomainResponse,
    EnrichIPRequest, EnrichIPResponse,
    EnrichURLRequest, EnrichURLResponse,
    TrainRequest, TrainResponse,
    PredictRequest, PredictionResult,
    LPRequest, LPResponse,
    StoreResultsRequest,
    StatusResponse,
    AttributeRequest, AttributeResponse,
    TieredAttribution, TierPrediction,
)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
neo4j_client: Optional[Neo4jClient] = None
model_trained: bool = False
last_training: Optional[str] = None
training_in_progress: bool = False
training_error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global neo4j_client, model_trained
    neo4j_client = Neo4jClient()
    neo4j_client.run_schema_migration()
    # Check if model artifacts exist
    if os.path.exists(os.path.join(config.MODEL_DIR, "gnn_model.pt")):
        model_trained = True
    print("TRAIL GNN service started — Neo4j connected, schema migrated.")
    yield
    if neo4j_client:
        neo4j_client.close()
    print("TRAIL GNN service stopped.")


app = FastAPI(
    title="TRAIL GNN Service",
    description="IOC enrichment and GNN-based APT attribution",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Enrichment endpoints (called by n8n Workflow 1)
# ---------------------------------------------------------------------------

@app.post("/enrich/domain", response_model=EnrichDomainResponse)
def enrich_domain_endpoint(req: EnrichDomainRequest):
    """Enrich a domain with DNS, lexical, and ASN features."""
    result = enrich_domain(req.domain)
    return EnrichDomainResponse(**result)


@app.post("/enrich/ip", response_model=EnrichIPResponse)
def enrich_ip_endpoint(req: EnrichIPRequest):
    """Enrich an IP address with country and ASN info."""
    result = enrich_ip(req.ip)
    return EnrichIPResponse(**result)


@app.post("/enrich/url", response_model=EnrichURLResponse)
def enrich_url_endpoint(req: EnrichURLRequest):
    """Enrich a URL with lexical features and HTTP HEAD data."""
    result = enrich_url(req.url)
    return EnrichURLResponse(**result)


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@app.get("/status", response_model=StatusResponse)
def status():
    """Health check: Neo4j connectivity, model state, graph stats."""
    connected = neo4j_client.verify_connectivity() if neo4j_client else False
    graph_stats = {}
    events_per_apt = {}
    if connected and neo4j_client:
        try:
            graph_stats = neo4j_client.get_graph_stats()
            events_per_apt = neo4j_client.get_events_per_apt()
        except Exception:
            pass
    return StatusResponse(
        service_status="training" if training_in_progress else "running",
        neo4j_connected=connected,
        model_trained=model_trained,
        last_training=last_training,
        graph_stats=graph_stats,
        events_per_apt=events_per_apt,
    )


# ---------------------------------------------------------------------------
# Training endpoint
# ---------------------------------------------------------------------------

def _run_training(k_folds: int, ae_epochs: int, gnn_epochs: int):
    """Background training task."""
    global model_trained, last_training, training_in_progress, training_error
    try:
        from .training import train_pipeline
        result = train_pipeline(
            client=neo4j_client,
            k_folds=k_folds,
            ae_epochs=ae_epochs,
            gnn_epochs=gnn_epochs,
        )
        model_trained = True
        last_training = result.get("timestamp", datetime.now().isoformat())
        training_error = None
    except Exception as e:
        training_error = traceback.format_exc()
        print(f"Training failed: {e}")
    finally:
        training_in_progress = False


@app.post("/train", response_model=TrainResponse)
def train(req: TrainRequest, background_tasks: BackgroundTasks):
    """
    Train autoencoders + GraphSAGE on the knowledge graph.

    Runs in background; poll /status to check progress.
    """
    global training_in_progress
    if training_in_progress:
        raise HTTPException(status_code=409, detail="Training already in progress")

    training_in_progress = True
    background_tasks.add_task(
        _run_training,
        k_folds=req.k_folds if req.k_folds else config.K_FOLDS,
        ae_epochs=req.ae_epochs if req.ae_epochs else config.AE_EPOCHS,
        gnn_epochs=req.gnn_epochs if req.gnn_epochs else config.GNN_EPOCHS,
    )

    return TrainResponse(
        status="training_started",
        message="Training started in background. Poll /status to monitor.",
        metrics={},
    )


# ---------------------------------------------------------------------------
# Label Propagation endpoint
# ---------------------------------------------------------------------------

@app.post("/label-propagation", response_model=LPResponse)
def run_label_propagation(req: LPRequest):
    """Run label propagation on the graph (standalone, no GNN)."""
    try:
        from .vocabularies import VocabularySet
        from .graph_export import export_graph
        from .label_propagation import lp_predict

        vocabs = VocabularySet.build_from_graph(neo4j_client)
        data = export_graph(neo4j_client, vocabs)

        iterations = req.iterations if req.iterations else config.LP_ITERATIONS
        predictions = lp_predict(data, iterations=iterations)

        results = [
            PredictionResult(
                event_id=str(p["event_idx"]),
                predicted_apt=p["predicted_apt"],
                confidence=p["confidence"],
                method="label_propagation",
            )
            for p in predictions
        ]

        return LPResponse(
            status="success",
            predictions=results,
            iterations=iterations,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Predict endpoint (combined GNN + LP)
# ---------------------------------------------------------------------------

@app.post("/predict")
def run_predict(req: PredictRequest):
    """Combined GNN + LP prediction on unlabeled events with tiered attribution."""
    if not model_trained:
        raise HTTPException(
            status_code=400,
            detail="Model not trained yet. Call /train first."
        )

    try:
        from .inference import predict as run_inference, compute_tiered_attribution

        alpha_gnn = req.alpha_gnn if req.alpha_gnn is not None else 0.6
        alpha_lp = req.alpha_lp if req.alpha_lp is not None else 0.4

        raw_results = run_inference(
            client=neo4j_client,
            event_ids=req.event_ids,
            alpha_gnn=alpha_gnn,
            alpha_lp=alpha_lp,
            include_labeled=req.include_labeled,
        )

        predictions = []
        for r in raw_results:
            combined_scores = r.get("combined_scores", {})
            tiered = compute_tiered_attribution(combined_scores) if combined_scores else None
            predictions.append({
                "event_id": r["event_id"],
                "predicted_apt": r["predicted_apt"],
                "confidence": r["confidence"],
                "method": "gnn+lp",
                "tiered": tiered,
            })

        return {
            "status": "success",
            "predictions": predictions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Store results back to Neo4j
# ---------------------------------------------------------------------------

@app.post("/store-results")
def store_results(req: StoreResultsRequest):
    """Write attribution predictions back to Neo4j as properties on Event nodes."""
    try:
        for pred in req.predictions:
            neo4j_client.run_write(
                "MATCH (e:Event {id: $event_id}) "
                "SET e.predicted_apt = $predicted_apt, "
                "    e.prediction_confidence = $confidence, "
                "    e.prediction_method = $method, "
                "    e.prediction_timestamp = datetime()",
                {
                    "event_id": pred.event_id,
                    "predicted_apt": pred.predicted_apt,
                    "confidence": pred.confidence,
                    "method": pred.method or "gnn+lp",
                },
            )
        return {"status": "success", "stored": len(req.predictions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Results query endpoint
# ---------------------------------------------------------------------------

@app.get("/results")
def get_results():
    """Fetch attribution results summary from Neo4j."""
    try:
        results = neo4j_client.run_query(
            "MATCH (e:Event) "
            "WHERE e.predicted_apt IS NOT NULL "
            "RETURN e.id AS event_id, e.name AS event_name, "
            "       e.apt AS known_apt, e.predicted_apt AS predicted_apt, "
            "       e.prediction_confidence AS confidence, "
            "       e.prediction_method AS method "
            "ORDER BY e.prediction_confidence DESC "
            "LIMIT 500"
        )

        summary = neo4j_client.run_query(
            "MATCH (e:Event) "
            "WHERE e.predicted_apt IS NOT NULL "
            "RETURN e.predicted_apt AS apt, count(*) AS count "
            "ORDER BY count DESC"
        )

        return {
            "status": "success",
            "total_predictions": len(results),
            "summary_by_apt": {r["apt"]: r["count"] for r in summary},
            "predictions": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Ad-hoc attribution — submit unknown IOCs for APT prediction
# ---------------------------------------------------------------------------

@app.post("/attribute", response_model=AttributeResponse)
def attribute_iocs(req: AttributeRequest):
    """
    Submit unknown IOCs (domains, IPs, URLs) for APT attribution.

    This endpoint:
      1. Enriches each IOC (DNS, ASN, lexical features)
      2. MERGEs them into the Neo4j knowledge graph
      3. Creates a temporary Event linked to these IOCs
      4. Runs the trained GNN + Label Propagation ensemble
      5. Returns the predicted APT group with confidence scores
      6. Cleans up the temporary Event (IOC nodes persist)
    """
    if not model_trained:
        raise HTTPException(
            status_code=400,
            detail="Model not trained yet. Call /train first."
        )

    if not req.iocs:
        raise HTTPException(status_code=400, detail="No IOCs provided")

    temp_event_id = f"attr_{uuid.uuid4().hex[:12]}"
    iocs_processed = 0

    try:
        # --- Step 1: Create temporary Event node ---
        neo4j_client.run_write(
            "CREATE (e:Event {id: $eid, name: 'Attribution query', "
            "source: 'attribute_api', created_at: datetime()})",
            {"eid": temp_event_id},
        )

        # --- Step 2: Enrich IOCs, MERGE into Neo4j, link to Event ---
        for ioc in req.iocs:
            ioc_type = ioc.type.lower().strip()
            ioc_value = ioc.value.strip()

            if ioc_type == "domain":
                enriched = enrich_domain(ioc_value)
                neo4j_client.run_write(
                    "MERGE (d:Domain {value: $value}) "
                    "SET d.tld = $tld, d.length = $length, "
                    "    d.digit_count = $digit_count, "
                    "    d.period_count = $period_count, "
                    "    d.entropy = $entropy, "
                    "    d.is_nxdomain = $is_nxdomain, "
                    "    d.active_period_days = $active_period_days, "
                    "    d.a_count = $a_count, d.aaaa_count = $aaaa_count, "
                    "    d.mx_count = $mx_count, d.ns_count = $ns_count, "
                    "    d.soa_count = $soa_count, d.txt_count = $txt_count, "
                    "    d.cname_count = $cname_count, d.ptr_count = $ptr_count, "
                    "    d.srv_count = $srv_count, "
                    "    d.country = $country, d.asn = $asn, "
                    "    d.asn_description = $asn_description "
                    "WITH d "
                    "MATCH (e:Event {id: $eid}) "
                    "MERGE (e)-[:InReport]->(d)",
                    {**enriched, "value": ioc_value, "eid": temp_event_id},
                )
                iocs_processed += 1

            elif ioc_type == "ip":
                enriched = enrich_ip(ioc_value)
                neo4j_client.run_write(
                    "MERGE (ip:IP {value: $value}) "
                    "SET ip.country = $country, ip.asn = $asn, "
                    "    ip.asn_description = $asn_description "
                    "WITH ip "
                    "MATCH (e:Event {id: $eid}) "
                    "MERGE (e)-[:InReport]->(ip)",
                    {**enriched, "value": ioc_value, "eid": temp_event_id},
                )
                iocs_processed += 1

            elif ioc_type == "url":
                enriched = enrich_url(ioc_value)
                neo4j_client.run_write(
                    "MERGE (u:URL {value: $value}) "
                    "SET u.tld = $tld, u.length = $length, "
                    "    u.digit_count = $digit_count, "
                    "    u.special_char_count = $special_char_count, "
                    "    u.path_depth = $path_depth, "
                    "    u.has_query = $has_query, "
                    "    u.has_fragment = $has_fragment, "
                    "    u.entropy = $entropy, "
                    "    u.file_extension = $file_extension, "
                    "    u.http_status = $http_status, "
                    "    u.content_type = $content_type, "
                    "    u.server = $server, "
                    "    u.head_failed = $head_failed "
                    "WITH u "
                    "MATCH (e:Event {id: $eid}) "
                    "MERGE (e)-[:InReport]->(u)",
                    {
                        "value": ioc_value,
                        "eid": temp_event_id,
                        "tld": enriched.get("tld", ""),
                        "length": enriched.get("length", 0),
                        "digit_count": enriched.get("digit_count", 0),
                        "special_char_count": enriched.get("special_char_count", 0),
                        "path_depth": enriched.get("path_depth", 0),
                        "has_query": enriched.get("has_query", False),
                        "has_fragment": enriched.get("has_fragment", False),
                        "entropy": enriched.get("entropy", 0.0),
                        "file_extension": enriched.get("file_extension", ""),
                        "http_status": enriched.get("http_status"),
                        "content_type": enriched.get("content_type", ""),
                        "server": enriched.get("server", ""),
                        "head_failed": enriched.get("head_failed", True),
                    },
                )
                iocs_processed += 1

            else:
                print(f"Warning: unknown IOC type '{ioc_type}', skipping")

        if iocs_processed == 0:
            # Clean up empty event
            neo4j_client.run_write(
                "MATCH (e:Event {id: $eid}) DETACH DELETE e",
                {"eid": temp_event_id},
            )
            raise HTTPException(status_code=400, detail="No valid IOCs processed")

        # --- Step 3: Run GNN + LP prediction ---
        from .inference import predict as run_inference, compute_tiered_attribution

        raw_results = run_inference(
            client=neo4j_client,
            event_ids=[temp_event_id],
            alpha_gnn=0.6,
            alpha_lp=0.4,
            include_labeled=True,  # our temp event has no label, but pass True to not skip
        )

        if not raw_results:
            raise HTTPException(
                status_code=500,
                detail="No prediction returned — event may not have linked to graph"
            )

        result = raw_results[0]

        # Compute tiered attribution (Unit 42-inspired)
        combined_scores = result.get("combined_scores", {})
        tiered = None
        if combined_scores:
            tiered_raw = compute_tiered_attribution(combined_scores)
            from .schemas import TieredAttribution, TierPrediction
            tiered = TieredAttribution(
                tier3_named_actor=TierPrediction(**tiered_raw["tier3_named_actor"]),
                tier2_nation_state=TierPrediction(**tiered_raw["tier2_nation_state"]),
                tier1_activity_cluster=TierPrediction(**tiered_raw["tier1_activity_cluster"]),
                recommended_tier=tiered_raw["recommended_tier"],
                summary=tiered_raw["summary"],
            )

        return AttributeResponse(
            status="success",
            predicted_apt=result["predicted_apt"],
            confidence=result["confidence"],
            scores=combined_scores,
            iocs_processed=iocs_processed,
            event_id=temp_event_id,
            tiered=tiered,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Attribution failed: {e}")
    finally:
        # --- Step 4: Clean up temporary Event ---
        try:
            neo4j_client.run_write(
                "MATCH (e:Event {id: $eid}) DETACH DELETE e",
                {"eid": temp_event_id},
            )
        except Exception:
            pass  # best-effort cleanup
