"""
Inference pipeline: Load trained models and predict APT attribution.

Combines GNN softmax probabilities with Label Propagation scores
using a weighted average (configurable alpha).
"""

import os

import torch
import torch.nn.functional as F
from torch_geometric.data import HeteroData

from . import config
from .neo4j_client import Neo4jClient
from .vocabularies import VocabularySet
from .graph_export import export_graph
from .autoencoders import AutoencoderSet
from .model import TRAILHeteroGNN
from .label_propagation import label_propagation


def _compute_event_features(data: HeteroData) -> torch.Tensor:
    """Mean-pool IOC encodings for each event (same logic as training)."""
    num_events = data["event"].num_nodes
    encoding_dim = config.AE_ENCODING_DIM
    event_feats = torch.zeros((num_events, encoding_dim), dtype=torch.float32)
    counts = torch.zeros(num_events, dtype=torch.float32)

    for edge_type in data.edge_types:
        src_type, rel, dst_type = edge_type
        if src_type == "event" and "in_report" in rel:
            ei = data[edge_type].edge_index
            dst_x = data[dst_type].x
            if dst_x is None or dst_x.shape[0] == 0:
                continue
            for col in range(ei.shape[1]):
                ev_idx = ei[0, col].item()
                ioc_idx = ei[1, col].item()
                if ioc_idx < dst_x.shape[0]:
                    event_feats[ev_idx] += dst_x[ioc_idx]
                    counts[ev_idx] += 1

    mask = counts > 0
    event_feats[mask] = event_feats[mask] / counts[mask].unsqueeze(1)
    return event_feats


def load_models(model_dir: str = config.MODEL_DIR) -> tuple:
    """
    Load all trained artifacts.

    Returns (vocabs, ae_set, gnn_state_dict).
    """
    vocabs = VocabularySet.load(os.path.join(model_dir, "vocabularies.json"))

    ae_set = AutoencoderSet()
    ae_set.load(model_dir)

    gnn_state = torch.load(
        os.path.join(model_dir, "gnn_model.pt"),
        weights_only=True
    )

    return vocabs, ae_set, gnn_state


def predict(
    client: Neo4jClient | None = None,
    event_ids: list[str] | None = None,
    alpha_gnn: float = 0.6,
    alpha_lp: float = 0.4,
    lp_iterations: int = config.LP_ITERATIONS,
    include_labeled: bool = False,
) -> list[dict]:
    """
    Run combined GNN + LP inference.

    Args:
        client: Neo4j connection (creates one if None)
        event_ids: Specific event IDs to predict. None = all unlabeled.
        alpha_gnn: Weight for GNN predictions in ensemble (default 0.6)
        alpha_lp: Weight for LP predictions in ensemble (default 0.4)
        lp_iterations: Number of LP iterations

    Returns:
        List of prediction dicts with event_id, predicted_apt,
        confidence, and per-method scores.
    """
    own_client = False
    if client is None:
        client = Neo4jClient()
        own_client = True

    try:
        # Load models
        vocabs, ae_set, gnn_state = load_models()

        # Export current graph
        data = export_graph(client, vocabs)

        # Encode with AEs
        d_enc, ip_enc, url_enc = ae_set.encode_all(
            data["domain"].x, data["ip"].x, data["url"].x
        )
        data["domain"].x = d_enc
        data["ip"].x = ip_enc
        data["url"].x = url_enc

        # Compute event features
        data["event"].x = _compute_event_features(data)

        # --- GNN inference ---
        metadata = data.metadata()
        gnn = TRAILHeteroGNN(metadata)
        gnn.load_state_dict(gnn_state)
        gnn.eval()

        with torch.no_grad():
            x_dict = {nt: data[nt].x for nt in data.node_types}
            out_dict = gnn(x_dict, data.edge_index_dict)
            gnn_logits = out_dict["event"]
            gnn_probs = F.softmax(gnn_logits, dim=-1)

        # --- Label Propagation ---
        lp_probs = label_propagation(data, iterations=lp_iterations)

        # --- Ensemble ---
        combined = alpha_gnn * gnn_probs + alpha_lp * lp_probs
        combined = combined / combined.sum(dim=-1, keepdim=True)  # re-normalize

        # Build results
        labels = data["event"].y
        train_mask = data["event"].train_mask

        # Reverse-map event indices to IDs
        idx_to_event_id = {v: k for k, v in data.event_id2idx.items()}

        results = []
        for i in range(data["event"].num_nodes):
            eid = idx_to_event_id.get(i, f"event_{i}")

            # Filter to requested event_ids if specified
            if event_ids and eid not in event_ids:
                continue

            # Skip already-labeled events unless explicitly requested
            if not include_labeled and event_ids is None and train_mask[i] and labels[i] >= 0:
                continue

            conf, pred_idx = combined[i].max(dim=0)
            apt_name = config.IDX_TO_APT.get(pred_idx.item(), "Unknown")

            results.append({
                "event_id": eid,
                "predicted_apt": apt_name,
                "confidence": round(conf.item(), 4),
                "gnn_scores": {
                    config.IDX_TO_APT[j]: round(gnn_probs[i, j].item(), 4)
                    for j in range(config.NUM_CLASSES)
                },
                "lp_scores": {
                    config.IDX_TO_APT[j]: round(lp_probs[i, j].item(), 4)
                    for j in range(config.NUM_CLASSES)
                },
                "combined_scores": {
                    config.IDX_TO_APT[j]: round(combined[i, j].item(), 4)
                    for j in range(config.NUM_CLASSES)
                },
            })

        return results

    finally:
        if own_client:
            client.close()


def predict_single_event(
    event_id: str,
    client: Neo4jClient | None = None,
    alpha_gnn: float = 0.6,
    alpha_lp: float = 0.4,
) -> dict:
    """Convenience wrapper for predicting a single event."""
    results = predict(
        client=client,
        event_ids=[event_id],
        alpha_gnn=alpha_gnn,
        alpha_lp=alpha_lp,
    )
    if results:
        return results[0]
    return {"event_id": event_id, "predicted_apt": "Unknown", "confidence": 0.0}


def compute_tiered_attribution(combined_scores: dict) -> dict:
    """
    Compute hierarchical attribution tiers from per-APT probability scores.

    Adapted from Palo Alto Unit 42's tiered attribution framework:
      Tier 3 — Named Actor (high confidence on specific APT)
      Tier 2 — Nation-State (aggregate probabilities by country)
      Tier 1 — Activity Cluster (broad category)

    Args:
        combined_scores: dict mapping APT names to probabilities
            e.g. {"APT28": 0.15, "APT29": 0.12, ...}

    Returns:
        dict with tier3, tier2, tier1 predictions and recommended tier.
    """
    # --- Tier 3: Named Actor ---
    best_apt = max(combined_scores, key=combined_scores.get)
    best_apt_conf = combined_scores[best_apt]

    if best_apt_conf >= config.TIER3_CONFIDENCE:
        tier3_assessment = "high_confidence"
    elif best_apt_conf >= config.TIER2_CONFIDENCE:
        tier3_assessment = "moderate_confidence"
    else:
        tier3_assessment = "low_confidence"

    # --- Tier 2: Nation-State ---
    nation_scores = {}
    for apt_name, prob in combined_scores.items():
        nation = config.APT_TO_NATION.get(apt_name, "Unknown")
        nation_scores[nation] = nation_scores.get(nation, 0.0) + prob

    best_nation = max(nation_scores, key=nation_scores.get)
    best_nation_conf = nation_scores[best_nation]

    if best_nation_conf >= config.TIER3_CONFIDENCE:
        tier2_assessment = "high_confidence"
    elif best_nation_conf >= config.TIER2_CONFIDENCE:
        tier2_assessment = "moderate_confidence"
    else:
        tier2_assessment = "low_confidence"

    # --- Tier 1: Activity Cluster ---
    # Broader grouping: state-sponsored vs cybercrime
    cluster_scores = {}
    state_nations = {"Russia", "China", "North Korea", "Vietnam"}
    for nation, prob in nation_scores.items():
        if nation in state_nations:
            cluster_scores["State-Sponsored"] = cluster_scores.get("State-Sponsored", 0.0) + prob
        elif nation == "Cybercrime":
            cluster_scores["Cybercrime"] = cluster_scores.get("Cybercrime", 0.0) + prob
        else:
            cluster_scores["Unknown"] = cluster_scores.get("Unknown", 0.0) + prob

    best_cluster = max(cluster_scores, key=cluster_scores.get)
    best_cluster_conf = cluster_scores[best_cluster]

    if best_cluster_conf >= config.TIER3_CONFIDENCE:
        tier1_assessment = "high_confidence"
    elif best_cluster_conf >= config.TIER2_CONFIDENCE:
        tier1_assessment = "moderate_confidence"
    else:
        tier1_assessment = "low_confidence"

    # --- Determine recommended tier ---
    if best_apt_conf >= config.TIER3_CONFIDENCE:
        recommended_tier = 3
        summary = f"High confidence: {best_apt} ({best_apt_conf:.0%})"
    elif best_nation_conf >= config.TIER2_CONFIDENCE:
        recommended_tier = 2
        summary = f"Moderate confidence {best_nation} state-sponsored activity, possibly {best_apt}"
    else:
        recommended_tier = 1
        summary = f"Low confidence — activity cluster: {best_cluster}"

    return {
        "tier3_named_actor": {
            "prediction": best_apt,
            "confidence": round(best_apt_conf, 4),
            "assessment": tier3_assessment,
        },
        "tier2_nation_state": {
            "prediction": best_nation,
            "confidence": round(best_nation_conf, 4),
            "assessment": tier2_assessment,
        },
        "tier1_activity_cluster": {
            "prediction": best_cluster,
            "confidence": round(best_cluster_conf, 4),
            "assessment": tier1_assessment,
        },
        "recommended_tier": recommended_tier,
        "summary": summary,
        "nation_scores": {k: round(v, 4) for k, v in nation_scores.items()},
    }
