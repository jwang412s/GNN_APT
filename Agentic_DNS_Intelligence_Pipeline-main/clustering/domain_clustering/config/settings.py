"""
Configuration for DNS-based Threat Intelligence Clustering Pipeline

Includes:
- Clustering parameters (DBSCAN, HDBSCAN)
- Feature weights 
- Incident ID policy 
- Output paths and thresholds
- Visualization and enrichment settings

Based on implementation of:
"Using DNS Patterns for Automated Cyber Threat Attribution" (Leite et al., 2024)
"""

import hashlib
from typing import List, Dict, Any

# Current code: Adjusted to feature stability order [1.2, 1.0, 0.3, 2.0, 1.8]
# Note: Registrar=2.0 is the highest weight, Email=0.3 is the lowest weight
CONFIG: Dict[str, Any] = {
    "weights": [1.2, 1.0, 0.3, 2.0, 1.8],     # Domain, Subdomains, Email, Registrar, ASN
    "missing_feature_mode": "drop_dim",        # drop_dim or penalize
    "dbscan": {
        "eps": 0.5,
        "min_samples": 2,
        "filter_threshold": 0.40  # Strong filter
    },
    "hdbscan": {
        "min_samples": 2,
        "min_cluster_size": 2,
        "filter_threshold": 0.20,  # Weak filter
        "persistence_threshold": 0.50  # Default persistence threshold
    },
    "dbscan_enabled": False,                   # Enable DBSCAN in combined strategy (default: HDBSCAN-only)
    "use_structural_quality": True,            # Paper metric interface
    "combine_strategy": "dbscan_then_hdbscan",
    "k": 10,
    "time_window_days": 150,
    "subdomain_sep": ";",
    "cache_dir": "distance_matrices",
    "matrix_dtype": "float32",
    "seed": 1337,


    # Current code: Changed to incident_id_policy, strategy=infrastructure_hash, features=[registrar_id, asn]
    # Note: Field names and internal keys need synchronized renaming, output format is "|"-separated readable ID
    "incident_id_policy": {
        "strategy": "infrastructure_hash",
        "features": ["registrar_id", "asn"],
        "id_format": "readable",
        "separator": "|"
    },
    "timestamp_policy": {
        "prefer": ["collection_date", "first_seen", "last_seen"],
        "fallback": "now_utc"
    },
    # Visualization configuration
    "viz": {
        "enabled": True,
        "mode": "auto",                 # values: auto, sample, cluster_medoids, off
        "pca_sample_size": 8000,
        "medoid_min_cluster_size": 5,
        "label_top_k_clusters": 15,
        "heatmap_max_n": 4000,
        "figsize_pca": [10, 7],
        "figsize_heatmap": [10, 10],
        "dpi": 200
    },
    # Enrichment quality thresholds
    "enrichment_report": {
        "min_accept_quality": 0.65,
        "warn_email_missing_gt": 0.50,
        "warn_subdomain_missing_gt": 0.60,
        "warn_registrar_missing_gt": 0.50
    },
    # Weight presets
    "presets": {
        "baseline": [1.0, 1.0, 1.0, 1.0, 1.0],
        "practical": [1.2, 1.0, 0.3, 2.0, 1.8],
        "conservative": [1.0, 1.2, 0.2, 1.2, 1.6]
    },
    "infra_debug_record_limit": 0,
    "infra_debug_assign_limit": 0
}


def set_config_preset(name: str) -> None:
    """
    Switch to a named weight preset
    
    Args:
        name: Preset name (baseline, practical, conservative)
    
    Raises:
        ValueError: If preset name is unknown
    """
    p = CONFIG["presets"].get(name)
    if not p:
        raise ValueError(f"Unknown preset: {name}. Choose from {list(CONFIG['presets'].keys())}")
    CONFIG["weights"] = list(p)
    print(f"Preset set to '{name}': weights={CONFIG['weights']}")


def get_config_signature() -> str:
    """
    Generate configuration signature for cache file naming
    
    Uses weights, missing_feature_mode, and time_window_days to generate
    a deterministic signature for distance matrix cache files.
    
    Returns:
        8-character hexadecimal signature string
    """
    key_params = f"{CONFIG['weights']}{CONFIG['missing_feature_mode']}{CONFIG['time_window_days']}"
    return hashlib.md5(key_params.encode()).hexdigest()[:8]

