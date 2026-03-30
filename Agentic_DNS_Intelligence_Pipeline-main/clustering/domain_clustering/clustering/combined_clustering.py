"""
Combined clustering strategy: DBSCAN + HDBSCAN

Implements the dual filtering and combination strategy from the pipeline.
Combines DBSCAN and HDBSCAN results with quality filtering.
Supports HDBSCAN-only mode when dbscan_enabled=False.
"""

import numpy as np
from typing import Tuple, Dict, List, Optional

from .dbscan_clustering import cluster_dbscan
from .hdbscan_clustering import cluster_hdbscan

# Note: filter_clusters_by_quality imported from quality module (Step 5)
# Using runtime import to avoid circular dependency issues


def cluster_combined(
    M: np.ndarray,
    config: Dict,
    records: List = None
) -> Tuple[np.ndarray, Dict[int, float], Dict[int, str], Dict[int, int], Optional[Dict[int, float]]]:
    """
    Combined clustering: DBSCAN filtered, then HDBSCAN on noise
    
    This implements the dual filtering strategy:
    1. Run DBSCAN and filter by quality (if dbscan_enabled=True)
    2. Run HDBSCAN on full matrix and filter by quality
    3. Combine results: DBSCAN clusters take precedence, HDBSCAN fills noise gaps
    
    If dbscan_enabled=False, runs HDBSCAN-only mode.
    
    Args:
        M: Distance matrix of shape (n, n)
        config: Configuration dict
        records: Domain records (required for structural quality filtering)
    
    Returns:
        final_labels: Combined cluster labels (continuous IDs, -1 for noise)
        quality_map: Cluster ID to quality score mapping
        source_algo_map: Cluster ID to algorithm name ("DBSCAN" or "HDBSCAN")
        cluster_sizes: Cluster ID to member count mapping
        persistence_map: Optional dict mapping cluster_id to persistence score (HDBSCAN only)
    """
    # Import here to avoid circular dependency (Step 5)
    from ..quality.quality_evaluator import filter_clusters_by_quality
    
    if records is None:
        raise ValueError("records parameter is required for quality filtering")
    
    dbscan_enabled = config.get("dbscan_enabled", False)
    
    print("\n" + "="*60)
    print("Running Combined Clustering Strategy")
    if not dbscan_enabled:
        print("[DBSCAN disabled — using HDBSCAN-only mode]")
    print("="*60)

    n = M.shape[0]

    if not dbscan_enabled:
        # HDBSCAN-only mode
        print("\nStep 1: HDBSCAN clustering (full matrix)")
        labels_hdb, _, persistence_raw = cluster_hdbscan(M, config)

        # Step 2: Filter HDBSCAN by quality
        print("Step 2: HDBSCAN quality filtering")
        labels_hdb_filt, q_hd = filter_clusters_by_quality(
            M, labels_hdb,
            config["hdbscan"]["filter_threshold"],
            config["use_structural_quality"],
            records
        )

        # Rebuild continuous ID mapping
        unique_ids = np.unique(labels_hdb_filt)
        unique_ids = unique_ids[unique_ids != -1]  # Remove noise

        id_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_ids)}
        id_mapping[-1] = -1  # Keep noise as -1

        # Apply mapping
        remapped_labels = np.array([id_mapping[label] for label in labels_hdb_filt])

        # Build quality_map, source_algo_map, and persistence_map for final IDs
        quality_map = {}
        source_algo_map = {}
        persistence_map = {}

        for old_id, new_id in id_mapping.items():
            if old_id == -1:
                continue
            quality_map[new_id] = q_hd.get(old_id, 0.5)
            source_algo_map[new_id] = "HDBSCAN"
            if persistence_raw and old_id in persistence_raw:
                persistence_map[new_id] = persistence_raw[old_id]

        # Build cluster_sizes after remapping
        cluster_sizes = {}
        for cid in unique_ids:
            if int(cid) == -1:
                continue
            new_cid = id_mapping[cid]
            cluster_sizes[int(new_cid)] = int(np.sum(remapped_labels == new_cid))

        n_final_clusters = len(unique_ids)
        n_final_noise = list(remapped_labels).count(-1)

        print(f"\n{'='*60}")
        print("HDBSCAN-Only Clustering Summary")
        print(f"{'='*60}")
        print(f"  Total clusters:     {n_final_clusters}")
        print(f"  Noise points:       {n_final_noise}")
        print(f"{'='*60}\n")

        return remapped_labels, quality_map, source_algo_map, cluster_sizes, persistence_map

    # Original combined strategy (DBSCAN + HDBSCAN)
    # Step 1: Run DBSCAN
    print("\nStep 1: DBSCAN clustering")
    labels_db, _ = cluster_dbscan(M, config)

    # Step 2: Filter DBSCAN by quality
    print("Step 2: DBSCAN quality filtering")
    labels_db_filt, q_db = filter_clusters_by_quality(
        M, labels_db,
        config["dbscan"]["filter_threshold"],
        config["use_structural_quality"],
        records
    )

    # Step 3: Find noise indices
    noise_mask = labels_db_filt == -1
    noise_indices = np.where(noise_mask)[0]
    print(f"Step 3: Found {len(noise_indices)} noise points for HDBSCAN")

    # Step 4: Run HDBSCAN on full matrix
    print("\nStep 4: HDBSCAN clustering (full matrix)")
    labels_hdb, _, persistence_raw = cluster_hdbscan(M, config)

    # Step 5: Filter HDBSCAN by quality
    print("Step 5: HDBSCAN quality filtering")
    labels_hdb_filt, q_hd = filter_clusters_by_quality(
        M, labels_hdb,
        config["hdbscan"]["filter_threshold"],
        config["use_structural_quality"],
        records
    )

    # Step 6: Combine strategies
    print("\nStep 6: Combining DBSCAN and HDBSCAN results")

    # Initialize final labels as noise
    final_labels = np.full(n, -1, dtype=np.int32)

    # Assign DBSCAN non-noise labels first
    dbscan_non_noise = labels_db_filt != -1
    final_labels[dbscan_non_noise] = labels_db_filt[dbscan_non_noise]

    # For noise positions, assign HDBSCAN non-noise labels with offset
    # Find max DBSCAN cluster ID
    max_db_id = labels_db_filt.max() if labels_db_filt.max() > -1 else -1
    offset = max_db_id + 1

    for idx in noise_indices:
        if labels_hdb_filt[idx] != -1:
            final_labels[idx] = labels_hdb_filt[idx] + offset

    # Rebuild continuous ID mapping
    unique_ids = np.unique(final_labels)
    unique_ids = unique_ids[unique_ids != -1]  # Remove noise

    id_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_ids)}
    id_mapping[-1] = -1  # Keep noise as -1

    # Apply mapping
    remapped_labels = np.array([id_mapping[label] for label in final_labels])

    # Build quality_map, source_algo_map, and persistence_map for final IDs
    quality_map = {}
    source_algo_map = {}
    persistence_map = {}

    for old_id, new_id in id_mapping.items():
        if old_id == -1:
            continue

        if old_id <= max_db_id:
            # From DBSCAN
            quality_map[new_id] = q_db.get(old_id, 0.5)
            source_algo_map[new_id] = "DBSCAN"
        else:
            # From HDBSCAN
            original_hdb_id = old_id - offset
            quality_map[new_id] = q_hd.get(original_hdb_id, 0.5)
            source_algo_map[new_id] = "HDBSCAN"
            if persistence_raw and original_hdb_id in persistence_raw:
                persistence_map[new_id] = persistence_raw[original_hdb_id]

    # Build cluster_sizes after remapping
    cluster_sizes = {}
    for cid in unique_ids:
        if int(cid) == -1:
            continue
        new_cid = id_mapping[cid]
        cluster_sizes[int(new_cid)] = int(np.sum(remapped_labels == new_cid))

    n_final_clusters = len(unique_ids)
    n_final_noise = list(remapped_labels).count(-1)
    n_dbscan_contrib = sum(1 for algo in source_algo_map.values() if algo == "DBSCAN")
    n_hdbscan_contrib = sum(1 for algo in source_algo_map.values() if algo == "HDBSCAN")

    print(f"\n{'='*60}")
    print("Combined Clustering Summary")
    print(f"{'='*60}")
    print(f"  Total clusters:     {n_final_clusters}")
    print(f"  From DBSCAN:        {n_dbscan_contrib}")
    print(f"  From HDBSCAN:       {n_hdbscan_contrib}")
    print(f"  Noise points:       {n_final_noise}")
    print(f"{'='*60}\n")

    return remapped_labels, quality_map, source_algo_map, cluster_sizes, persistence_map

