"""
HDBSCAN clustering implementation for DNS domain records

Implements HDBSCAN clustering with precomputed distance matrices.
"""

import numpy as np
import hdbscan
from typing import Tuple, Dict, Optional


def cluster_hdbscan(M: np.ndarray, config: Dict) -> Tuple[np.ndarray, hdbscan.HDBSCAN, Optional[Dict[int, float]]]:
    """
    Run HDBSCAN clustering with precomputed distances
    
    Args:
        M: Precomputed distance matrix of shape (n, n)
        config: Configuration dict with 'hdbscan' parameters
    
    Returns:
        labels: Cluster labels (-1 for noise)
        model: Fitted HDBSCAN model
        persistence: Optional dict mapping cluster_id to persistence score
    """
    min_samples = config["hdbscan"]["min_samples"]
    min_cluster_size = config["hdbscan"]["min_cluster_size"]

    model = hdbscan.HDBSCAN(
        min_samples=min_samples,
        min_cluster_size=min_cluster_size,
        metric="precomputed",
        store_cluster_persistence=True  # Enable persistence computation
    )
    labels = model.fit_predict(M)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    print(f"  HDBSCAN: {n_clusters} clusters, {n_noise} noise points")

    # Extract persistence scores
    persistence = None
    if hasattr(model, 'cluster_persistence_') and model.cluster_persistence_ is not None:
        persistence = {}
        unique_labels = set(labels)
        unique_labels.discard(-1)
        
        # Map cluster labels to persistence scores
        for label in unique_labels:
            if label < len(model.cluster_persistence_):
                persistence[int(label)] = float(model.cluster_persistence_[label])

    return labels, model, persistence

