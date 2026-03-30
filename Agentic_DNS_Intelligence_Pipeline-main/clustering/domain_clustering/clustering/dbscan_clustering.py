"""
DBSCAN clustering implementation for DNS domain records

Implements DBSCAN clustering with precomputed distance matrices.
"""

import numpy as np
from typing import Tuple, Dict
from sklearn.cluster import DBSCAN


def cluster_dbscan(M: np.ndarray, config: Dict) -> Tuple[np.ndarray, DBSCAN]:
    """
    Run DBSCAN clustering with precomputed distances
    
    Args:
        M: Precomputed distance matrix of shape (n, n)
        config: Configuration dict with 'dbscan' parameters
    
    Returns:
        labels: Cluster labels (-1 for noise)
        model: Fitted DBSCAN model
    """
    eps = config["dbscan"]["eps"]
    min_samples = config["dbscan"]["min_samples"]

    model = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed")
    labels = model.fit_predict(M)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    print(f"  DBSCAN: {n_clusters} clusters, {n_noise} noise points (eps={eps})")

    return labels, model

