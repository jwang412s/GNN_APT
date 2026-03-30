"""
Distance matrix computation with caching

Builds pairwise distance matrices with intelligent caching for performance.
"""

import numpy as np
import hashlib
from pathlib import Path
from typing import List, Dict

from ..models import DomainRecord
from ..metrics import compute_pair_distance
from ..config import get_config_signature
from tqdm import tqdm


def build_distance_matrix(records: List[DomainRecord], config: Dict) -> np.ndarray:
    """
    Build pairwise distance matrix with caching
    
    Returns:
        Symmetric distance matrix of shape (n, n)
    """
    n = len(records)
    cache_dir = Path(config["cache_dir"])
    cache_dir.mkdir(exist_ok=True)
    
    # Generate cache filename with dataset signature
    preset_name = "practical" if config["weights"] == [1.2, 1.6, 0.4, 1.0, 1.3] else "custom"
    dataset_sig = hashlib.md5(str(n).encode()).hexdigest()[:6]
    cache_file = cache_dir / f"dm_{preset_name}_win{config['time_window_days']}_{dataset_sig}_{get_config_signature()}.npy"
    
    # Try loading from cache
    if cache_file.exists():
        print(f"✓ Loading cached distance matrix from {cache_file}")
        M = np.load(cache_file)
        if M.shape == (n, n):
            return M.astype(np.float64)  # Always return float64 for HDBSCAN
        else:
            print(f"  ⚠ Cache shape mismatch: {M.shape} != ({n}, {n}), recomputing...")
    
    # Compute distance matrix
    print(f"Computing distance matrix for {n} records...")
    M = np.zeros((n, n), dtype=np.float64)  # Always use float64 for HDBSCAN compatibility
    
    # Compute upper triangle (symmetric matrix)
    for i in tqdm(range(n), desc="Building distance matrix"):
        for j in range(i + 1, n):
            dist = compute_pair_distance(records[i], records[j], config)
            M[i, j] = dist
            M[j, i] = dist  # Mirror to lower triangle
    
    # Save to cache as float64
    np.save(cache_file, M.astype(np.float64))
    print(f"✓ Cached distance matrix to {cache_file}")
    
    return M.astype(np.float64)

