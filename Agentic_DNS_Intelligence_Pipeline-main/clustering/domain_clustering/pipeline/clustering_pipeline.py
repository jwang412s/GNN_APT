"""
Main clustering pipeline orchestration

Implements the complete clustering and incident similarity pipeline with
Structural Quality evaluation and infrastructure-based incident grouping.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import timezone
from typing import Optional, Dict
from pathlib import Path

from ..processing import load_data, apply_time_window, ensure_event_fields, sanitize_record
from ..processing import build_distance_matrix
from ..clustering import cluster_combined
from ..incident import build_incidents_from_infrastructure
from .enrichment_report import build_enrichment_report, suggest_preset_from_enrichment
from .visualization import visualize_clusters_pca, visualize_distance_heatmap
from ..config import CONFIG


def run_pipeline(
    enriched_path: str,
    labeled_path: Optional[str] = None,
    config: Optional[Dict] = None
):
    """
    Main clustering and incident similarity pipeline
    
    Builds campaign cluster patterns for threat actor attribution
    and identifies similar incidents based on DNS fingerprints.
    
    Args:
        enriched_path: Path to enriched domain CSV/Parquet
        labeled_path: Optional path to labeled data for evaluation
        config: Configuration dictionary (defaults to CONFIG)
    """
    if config is None:
        config = CONFIG
    
    # Create output directory
    RUN_DIR = "clustering_output"
    os.makedirs(RUN_DIR, exist_ok=True)
    
    print("\n" + "="*60)
    print("DNS-Based Threat Actor Attribution Pipeline")
    print("="*60)
    print(f"Configuration:")
    print(f"  Weights: {config['weights']}")
    print(f"  Missing mode: {config['missing_feature_mode']}")
    print(f"  Time window: {config['time_window_days']} days")
    print(f"  DBSCAN eps: {config['dbscan']['eps']}")
    print(f"  Quality filtering: {config['use_structural_quality']}")
    print("="*60)
    
    # Step 1: Load and preprocess data
    print("\n[Step 1/8] Loading and preprocessing data...")
    df = load_data(enriched_path)
    df = ensure_event_fields(df, config)
    df = apply_time_window(df, config["time_window_days"])
    
    if len(df) == 0:
        print("✗ No records after filtering, exiting")
        return
    
    # Normalize records
    print("  Normalizing records...")
    records = [sanitize_record(row, config) for _, row in df.iterrows()]
    print(f"✓ Normalized {len(records)} records")
    record_debug_limit = config.get("infra_debug_record_limit", 0)
    if record_debug_limit > 0:
        print("=== DATA LOADING DEBUG ===")
        for i, record in enumerate(records[:record_debug_limit]):
            print(f"Record {i}:")
            print(f"  registrar_name type: {type(record.registrar_name)}, value: {record.registrar_name}")
            print(f"  registrar_id type: {type(record.registrar_id)}, value: {record.registrar_id}")
            print(f"  asn type: {type(record.asn)}, value: {record.asn}")
    
    # Build and save enrichment quality report
    print("  Building enrichment quality report...")
    rep = build_enrichment_report(df, config)
    with open(os.path.join(RUN_DIR, "enrichment_report.json"), "w") as f:
        json.dump(rep, f, indent=2)
    with open(os.path.join(RUN_DIR, "enrichment_report.txt"), "w") as f:
        f.write(json.dumps(rep, indent=2))
    
    print(f"Enrichment quality: overall={rep['overall_quality']:.3f}, present_rates={rep['present_rates']}")
    if rep["overall_quality"] < config["enrichment_report"]["min_accept_quality"]:
        print("  CRITICAL: quality below threshold. Consider preset 'conservative' or improve data sources.")
    
    # Suggest presets based on enrichment
    suggest_preset_from_enrichment(rep)
    
    # Step 2: Build distance matrix
    print("\n[Step 2/8] Building distance matrix...")
    M = build_distance_matrix(records, config)
    
    # Step 3: Run combined clustering
    print("\n[Step 3/8] Running clustering...")
    # ⭐ Modified: pass records for Structural Quality evaluation
    final_labels, quality_map, source_algo_map, cluster_sizes, persistence_map = cluster_combined(M, config, records=records)
    
    # Step 4: Build campaign cluster patterns
    print("\n[Step 4/8] Building campaign cluster patterns...")
    
    incidents = build_incidents_from_infrastructure(records, final_labels)
    # Derive event_tags from incidents for downstream recommend_top_k()
    event_tags = {
        incident["incident_id"]: set(incident["pattern_set"])
        for incident in incidents.values()
    }
    
    # Step 5: Save clustering results
    print("\n[Step 5/8] Saving clustering results...")
    
    # Add cluster info to DataFrame
    df["cluster_id"] = final_labels
    df["cluster_quality"] = df["cluster_id"].map(quality_map).fillna(0.0)
    df["source_algo"] = df["cluster_id"].map(source_algo_map).fillna("NOISE")
    
    # Add persistence column if available
    if persistence_map:
        df["cluster_persistence"] = df["cluster_id"].map(persistence_map)
    else:
        df["cluster_persistence"] = np.nan
    
    # Save clustering result table
    clustering_out = os.path.join(RUN_DIR, "clustering_results.csv")
    df.to_csv(clustering_out, index=False)
    print(f"✓ Saved clustering results to {clustering_out}")
    
    # Save campaign patterns (incident-level cluster patterns)
    rows = []
    for ev, s in event_tags.items():
        if not s:
            continue
        rows.append({
            "incident_id": ev,
            "pattern_set": ";".join(str(x) for x in sorted(s))
        })
    campaign_df = pd.DataFrame(rows)
    campaign_df.sort_values("incident_id", inplace=True)
    campaign_out = os.path.join(RUN_DIR, "campaign_patterns.csv")
    campaign_df.to_csv(campaign_out, index=False)
    print(f"✓ Saved campaign cluster patterns to {campaign_out}")
    
    # Optional: Save incidents detailed information
    incidents_out = os.path.join(RUN_DIR, "incidents_detailed.json")
    incidents_for_json = {
        eid: {
            "incident_id": info["incident_id"],
            "registrar_id": info["registrar_id"],
            "asn": info["asn"],
            "domain_count": info["domain_count"],
            "cluster_count": info["cluster_count"],
            "domains": info["domains"],  # List of all domains
            "pattern_set": info["pattern_set"]
        }
        for eid, info in incidents.items()
    }
    with open(incidents_out, 'w') as f:
        json.dump(incidents_for_json, f, indent=2)
    print(f"✓ Saved detailed incidents to {incidents_out}")
    
    # Step 6: Generate visualizations
    print("\n[Step 6/8] Generating visualizations...")
    try:
        visualize_clusters_pca(M, final_labels, out_path=os.path.join(RUN_DIR, "clustering_pca.png"), config=config)
        visualize_distance_heatmap(M, final_labels, out_path=os.path.join(RUN_DIR, "clustering_heatmap.png"), config=config)
    except Exception as e:
        print(f"⚠ Visualization failed: {e}")
    
    # Step 7: Evaluation (if labeled data provided)
    if labeled_path:
        print("\n[Step 7/8] Running evaluation...")
        try:
            df_labeled = load_data(labeled_path)
            df_labeled = ensure_event_fields(df_labeled, config)
            df_labeled = apply_time_window(df_labeled, config["time_window_days"])
            
            # Build labeled event tags (simplified - would need full clustering)
            # For now, skip detailed evaluation
            print("  ⚠ Evaluation requires labeled data to be clustered separately")
            print("  Skipping detailed evaluation for now")
            
        except Exception as e:
            print(f"⚠ Evaluation failed: {e}")
    else:
        print("\n[Step 7/8] Skipping evaluation (no labeled data provided)")
    
    # Step 8: Generate summary report
    print("\n[Step 8/8] Generating summary report...")
    
    # Compute extended statistics
    dbscan_clusters = sum(1 for a in source_algo_map.values() if a == "DBSCAN")
    hdbscan_clusters = sum(1 for a in source_algo_map.values() if a == "HDBSCAN")
    total_clusters = len(quality_map)
    n_noise = int((final_labels == -1).sum())
    
    # Compute persistence statistics
    persistence_stats = None
    if persistence_map and len(persistence_map) > 0:
        persistence_values = [v for v in persistence_map.values() if v is not None]
        if persistence_values:
            persistence_threshold = config.get("hdbscan", {}).get("persistence_threshold", 0.50)
            valid_clusters = [v for v in persistence_values if v >= persistence_threshold]
            persistence_stats = {
                "min": float(np.min(persistence_values)),
                "max": float(np.max(persistence_values)),
                "mean": float(np.mean(persistence_values)),
                "valid_clusters": len(valid_clusters),
                "ratio_valid": len(valid_clusters) / len(persistence_values) if persistence_values else 0.0,
                "histogram": [
                    float(np.histogram(persistence_values, bins=10, range=(0.0, 1.0))[0][i])
                    for i in range(10)
                ]
            }
    
    # Compute cluster stats extended
    avg_quality = float(np.mean(list(quality_map.values()))) if quality_map else 0.0
    avg_persistence = float(np.mean(list(persistence_map.values()))) if persistence_map and len(persistence_map) > 0 else None
    
    # Count core clusters (quality >= 0.6 and persistence >= 0.5)
    core_cluster_count = 0
    if persistence_map:
        for cid in quality_map.keys():
            quality_val = quality_map.get(cid, 0.0)
            persistence_val = persistence_map.get(cid)
            if quality_val >= 0.6 and persistence_val is not None and persistence_val >= 0.5:
                core_cluster_count += 1
    else:
        # If no persistence, count clusters with quality >= 0.6
        core_cluster_count = sum(1 for q in quality_map.values() if q >= 0.6)
    
    cluster_stats_extended = {
        "total_clusters": total_clusters,
        "dbscan_clusters": dbscan_clusters,
        "hdbscan_clusters": hdbscan_clusters,
        "noise_points": n_noise,
        "avg_quality": avg_quality,
        "avg_persistence": avg_persistence,
        "num_core_clusters": core_cluster_count,
        "ratio_core_clusters": core_cluster_count / total_clusters if total_clusters > 0 else 0.0
    }
    
    summary = {
        "timestamp": pd.Timestamp.now(tz=timezone.utc).isoformat(),
        "config": {
            "weights": config["weights"],
            "missing_mode": config["missing_feature_mode"],
            "time_window_days": config["time_window_days"],
            "dbscan_eps": config["dbscan"]["eps"],
            "dbscan_filter": config["dbscan"]["filter_threshold"],
            "hdbscan_filter": config["hdbscan"]["filter_threshold"],
            "dbscan_enabled": config.get("dbscan_enabled", False)
        },
        "data": {
            "total_records": len(df),
            "total_incidents": len(event_tags)
        },
        "clustering": {
            "n_clusters": total_clusters,
            "n_noise": n_noise,
            "dbscan_clusters": dbscan_clusters,
            "hdbscan_clusters": hdbscan_clusters
        },
        "quality": {
            "avg_cluster_quality": avg_quality,
            "min_cluster_quality": float(np.min(list(quality_map.values()))) if quality_map else 0.0,
            "max_cluster_quality": float(np.max(list(quality_map.values()))) if quality_map else 0.0
        },
        "cluster_stats_extended": cluster_stats_extended
    }
    
    # Add persistence stats if available
    if persistence_stats:
        summary["hdbscan_persistence_stats"] = persistence_stats
    
    summary_out = os.path.join(RUN_DIR, "clustering_summary.json")
    with open(summary_out, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✓ Saved summary to {summary_out}")
    
    # Print core clusters summary
    print(f"\nCore clusters (quality>=0.6 & persistence>=0.5): {core_cluster_count}/{total_clusters} ({100.0 * core_cluster_count / total_clusters if total_clusters > 0 else 0.0:.1f}%)")
    
    print("\n" + "="*60)
    print("Pipeline Complete!")
    print("="*60)
    print(f"\nOutputs in {RUN_DIR}/:")
    print(f"  - clustering_results.csv (per-domain clustering results)")
    print(f"  - campaign_patterns.csv (incident-level cluster patterns)")
    print(f"  - enrichment_report.json (enrichment quality report)")
    print(f"  - clustering_pca.png (PCA visualization)")
    print(f"  - clustering_heatmap.png (distance heatmap)")
    print(f"  - clustering_summary.json (summary statistics)")
    print("="*60 + "\n")

