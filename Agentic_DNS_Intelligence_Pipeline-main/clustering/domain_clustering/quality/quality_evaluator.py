"""
Quality evaluation orchestration

Coordinates between structural quality (Dupont method) and fallback methods.
"""

import numpy as np
from typing import Dict, Tuple, Optional, List

from ..models import DomainRecord
from .structural_quality import filter_clusters_by_structural_quality


def filter_clusters_by_quality(
    M: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    use_structural_quality: bool,
    records: Optional[List[DomainRecord]] = None
) -> Tuple[np.ndarray, Dict[int, float]]:
    """
    Filter clusters by quality threshold
    
    Main entry point for quality filtering. Supports both structural quality
    (Dupont method) and fallback to silhouette-based method.
    
    Args:
        M: Distance matrix
        labels: Cluster labels
        threshold: Minimum quality score
        use_structural_quality: Use Dupont method if True, else silhouette
        records: Domain records (required for structural quality)
    
    Returns:
        filtered_labels: Labels with low-quality clusters marked as noise
        quality_map: Cluster ID to quality score mapping
    """
    if use_structural_quality:
        if records is None:
            raise ValueError("records parameter required for structural quality method")
        return filter_clusters_by_structural_quality(
            M, labels, records, threshold, None
        )
    else:
        # Fallback to silhouette-based method (from legacy code)
        from sklearn.metrics import silhouette_samples
        
        unique_labels = set(labels)
        unique_labels.discard(-1)
        
        # Early exit conditions
        if len(unique_labels) <= 1:
            return labels.copy(), {}
        
        # Compute quality scores using silhouette
        try:
            silhouette_vals = silhouette_samples(M, labels, metric="precomputed")
            quality_map = {}
            for label in unique_labels:
                mask = labels == label
                quality_map[label] = float(np.mean(silhouette_vals[mask]))
        except Exception as e:
            print(f"  ⚠ Quality computation failed: {e}, keeping all clusters")
            return labels.copy(), {}
        
        # Filter low-quality clusters
        filtered_labels = labels.copy()
        filtered_count = 0
        
        for label, quality in quality_map.items():
            if quality < threshold:
                filtered_labels[filtered_labels == label] = -1
                filtered_count += 1
        
        if filtered_count > 0:
            print(f"  Filtered {filtered_count} low-quality clusters (threshold={threshold:.2f})")
        
        return filtered_labels, quality_map


class QualityEvaluator:
    """
    Orchestrates quality evaluation and filtering
    
    Provides a class-based interface for quality evaluation with configurable
    methods and thresholds.
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize quality evaluator
        
        Args:
            config: Configuration dict
        """
        self.config = config or {}
    
    def evaluate_cluster_quality(
        self,
        M: np.ndarray,
        labels: np.ndarray,
        records: List[DomainRecord],
        threshold: float = 0.4,
        use_structural_quality: bool = True
    ) -> Tuple[np.ndarray, Dict[int, float]]:
        """
        Evaluate and filter clusters by quality
        
        Args:
            M: Distance matrix
            labels: Cluster labels
            records: Domain records
            threshold: Quality threshold
            use_structural_quality: Use Dupont method
        
        Returns:
            (filtered_labels, quality_map)
        """
        return filter_clusters_by_quality(
            M, labels, threshold, use_structural_quality, records
        )

