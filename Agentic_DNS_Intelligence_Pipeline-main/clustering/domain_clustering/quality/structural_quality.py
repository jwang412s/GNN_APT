"""
Structural Quality Scoring for DNS Clusters

Based on Dupont et al. (2021) "Similarity-Based Clustering For IoT Device Classification"
Adapted for DNS threat intelligence clustering

Core method:
  - Compute per-feature average dissimilarity AD_i for each cluster
  - Cluster is "good" if >= t_good features have AD_i < t_diss
  - Provides interpretable quality metrics
"""

import numpy as np
from typing import Dict, List, Tuple, Any, Optional, Set
from dataclasses import dataclass

from ..models import DomainRecord
from ..metrics.distance_metrics import lev_norm, jaccard_dist, registrar_dist, asn_dist

# Thresholds (based on Dupont paper empirical values)
T_DISS = 0.2      # Feature similarity threshold
T_GOOD = 3        # Minimum similar features required (out of 5)


@dataclass
class FeatureQualityMetrics:
    """Single feature quality for a cluster"""
    feature_name: str
    avg_dissimilarity: float
    is_similar: bool  # True if avg_dissimilarity < T_DISS
    num_pairs: int    # Number of valid pairs used


@dataclass
class ClusterQualityResult:
    """Complete structural quality for a cluster"""
    cluster_id: int
    overall_quality_score: float  # [0, 1]
    is_good: bool  # True if >= t_good similar features
    feature_metrics: List[FeatureQualityMetrics]
    similar_feature_count: int
    total_feature_count: int


def compute_feature_dissimilarity(
    records_in_cluster: List[DomainRecord],
    feature_name: str
) -> Tuple[float, int]:
    """
    Compute average dissimilarity for a single feature (AD_i)
    
    Args:
        records_in_cluster: All records in cluster
        feature_name: Feature name ('domain', 'subdomains', 'email_user', 'registrar', 'asn')
    
    Returns:
        (avg_dissimilarity, num_pairs)
    """
    if len(records_in_cluster) < 2:
        return 0.0, 0
    
    n = len(records_in_cluster)
    dissim_values = []
    
    for i in range(n):
        for j in range(i+1, n):
            rec_i = records_in_cluster[i]
            rec_j = records_in_cluster[j]
            
            # Compute dissimilarity based on feature type
            if feature_name == 'domain':
                dist = lev_norm(rec_i.domain, rec_j.domain)
            elif feature_name == 'subdomains':
                dist = jaccard_dist(rec_i.subdomains, rec_j.subdomains)
            elif feature_name == 'email_user':
                dist = lev_norm(rec_i.email_user, rec_j.email_user)
            elif feature_name == 'registrar':
                dist = registrar_dist(rec_i, rec_j)
            elif feature_name == 'asn':
                dist = asn_dist(rec_i, rec_j)
            else:
                continue
            
            dissim_values.append(dist)
    
    if not dissim_values:
        return 1.0, 0
    
    avg_dissim = float(np.mean(dissim_values))
    return avg_dissim, len(dissim_values)


def compute_cluster_structural_quality(
    records_in_cluster: List[DomainRecord],
    config: Optional[dict] = None,
    cluster_id: int = -1
) -> ClusterQualityResult:
    """
    Compute structural quality score for a cluster (Dupont method)
    
    Args:
        records_in_cluster: All records in cluster
        config: Configuration dict (unused, for future compatibility)
        cluster_id: Cluster ID
    
    Returns:
        ClusterQualityResult object
    """
    # Define features (names only, functions are determined in compute_feature_dissimilarity)
    features = [
        'domain',
        'subdomains',
        'email_user',
        'registrar',
        'asn'
    ]
    
    feature_metrics = []
    similar_count = 0
    
    for feature_name in features:
        avg_dissim, num_pairs = compute_feature_dissimilarity(
            records_in_cluster,
            feature_name
        )
        
        is_similar = avg_dissim < T_DISS
        if is_similar:
            similar_count += 1
        
        metrics = FeatureQualityMetrics(
            feature_name=feature_name,
            avg_dissimilarity=float(avg_dissim),
            is_similar=is_similar,
            num_pairs=int(num_pairs)
        )
        feature_metrics.append(metrics)
    
    # Overall quality score [0, 1]
    total_features = len(features)
    overall_score = similar_count / total_features
    
    # Is this a "good" cluster?
    is_good = similar_count >= T_GOOD
    
    result = ClusterQualityResult(
        cluster_id=int(cluster_id),
        overall_quality_score=float(overall_score),
        is_good=is_good,
        feature_metrics=feature_metrics,
        similar_feature_count=int(similar_count),
        total_feature_count=int(total_features)
    )
    
    return result


def compute_structural_quality_map(
    records: List[DomainRecord],
    final_labels: np.ndarray,
    M: Optional[np.ndarray] = None,
    config: Optional[dict] = None
) -> Tuple[Dict[int, float], Dict[int, ClusterQualityResult], Dict[int, Dict[str, Any]]]:
    """
    Compute structural quality scores for all clusters
    
    Handles singleton (size=1) and pair (size=2) clusters with special quality rules.
    
    Args:
        records: All domain records
        final_labels: Cluster labels
        M: Distance matrix (required for pair cluster quality computation)
        config: Configuration dict
    
    Returns:
        (quality_map, detailed_results, cluster_flags)
        - quality_map: Dict[cluster_id → quality_score ∈ [0,1]]
        - detailed_results: Dict[cluster_id → ClusterQualityResult]
        - cluster_flags: Dict[cluster_id → {"is_singleton": bool, "is_pair": bool}]
    """
    unique_labels = set(final_labels)
    unique_labels.discard(-1)  # Remove noise
    
    quality_map = {}
    detailed_results = {}
    cluster_flags = {}
    
    singleton_count = 0
    pair_count = 0
    
    for cluster_id in unique_labels:
        mask = final_labels == cluster_id
        cluster_records = [records[i] for i in range(len(records)) if mask[i]]
        
        if not cluster_records:
            continue
        
        cluster_size = len(cluster_records)
        flags = {"is_singleton": False, "is_pair": False}
        
        # Handle singleton clusters (size=1)
        if cluster_size == 1:
            quality_map[int(cluster_id)] = 0.0
            flags["is_singleton"] = True
            singleton_count += 1
            # Create minimal result for singleton
            result = ClusterQualityResult(
                cluster_id=int(cluster_id),
                overall_quality_score=0.0,
                is_good=False,
                feature_metrics=[],
                similar_feature_count=0,
                total_feature_count=5
            )
            detailed_results[int(cluster_id)] = result
        # Handle pair clusters (size=2)
        elif cluster_size == 2:
            flags["is_pair"] = True
            pair_count += 1
            # Compute quality as 1 - distance between the pair
            if M is not None:
                indices = [i for i in range(len(records)) if mask[i]]
                if len(indices) == 2:
                    pair_distance = M[indices[0], indices[1]]
                    pair_quality = 1.0 - float(pair_distance)
                    quality_map[int(cluster_id)] = max(0.0, min(1.0, pair_quality))
                else:
                    quality_map[int(cluster_id)] = 0.5  # Fallback
            else:
                quality_map[int(cluster_id)] = 0.5  # Fallback if M not provided
            
            # Create result for pair
            result = compute_cluster_structural_quality(
                cluster_records,
                config,
                cluster_id=int(cluster_id)
            )
            # Override with pair-based quality
            result.overall_quality_score = quality_map[int(cluster_id)]
            detailed_results[int(cluster_id)] = result
        else:
            # Normal cluster (size >= 3)
            result = compute_cluster_structural_quality(
                cluster_records,
                config,
                cluster_id=int(cluster_id)
            )
            quality_map[int(cluster_id)] = result.overall_quality_score
            detailed_results[int(cluster_id)] = result
        
        cluster_flags[int(cluster_id)] = flags
    
    # Print report
    if len(quality_map) > 0:
        good_clusters = sum(1 for v in quality_map.values() if v >= 0.6)
        avg_quality = float(np.mean(list(quality_map.values())))
        print(f"\n【Structural Quality Report】")
        print(f"  Total clusters: {len(quality_map)}")
        print(f"  Singleton clusters: {singleton_count}")
        print(f"  Pair clusters: {pair_count}")
        print(f"  Good clusters (quality >= 0.6): {good_clusters}")
        print(f"  Average quality: {avg_quality:.3f}")
        print(f"  Threshold (T_DISS={T_DISS}, T_GOOD={T_GOOD})")
    
    return quality_map, detailed_results, cluster_flags


def filter_clusters_by_structural_quality(
    M: Optional[np.ndarray],
    labels: np.ndarray,
    records: List[DomainRecord],
    threshold: float = 0.4,
    config: Optional[dict] = None
) -> Tuple[np.ndarray, Dict[int, float]]:
    """
    Filter clusters by structural quality threshold
    
    Note: Singleton and pair clusters are kept (not filtered) but have special quality scores.
    
    Args:
        M: Distance matrix (required for pair cluster quality computation)
        labels: Cluster labels
        records: All domain records
        threshold: Quality threshold (default 0.4 = 2/5 features)
        config: Configuration dict
    
    Returns:
        (filtered_labels, quality_map)
    """
    quality_map, _, cluster_flags = compute_structural_quality_map(records, labels, M, config)
    
    filtered_labels = labels.copy()
    filtered_count = 0
    
    for cluster_id, quality in quality_map.items():
        # Don't filter singleton/pair clusters, but mark low-quality normal clusters as noise
        flags = cluster_flags.get(cluster_id, {})
        if not flags.get("is_singleton", False) and not flags.get("is_pair", False):
            if quality < threshold:
                filtered_labels[labels == cluster_id] = -1
                filtered_count += 1
    
    if filtered_count > 0:
        print(f"  Filtered {filtered_count} low-quality clusters (threshold={threshold:.2f})")
    
    return filtered_labels, quality_map

