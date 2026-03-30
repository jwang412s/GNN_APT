"""
Evaluation metrics for recommender system

Implements top-k recommendation and evaluation functions for
incident similarity based on campaign cluster patterns.
"""

import numpy as np
import pandas as pd
from typing import Dict, Set

from ..metrics import jaccard_similarity


def recommend_top_k(
    query_incident_id: str,
    event_tags: Dict[str, Set[int]],
    k: int,
    quality_map: Dict[int, float],
    source_algo_map: Dict[int, str],
    cluster_sizes: Dict[int, int]
) -> pd.DataFrame:
    """
    Generate top-k similar incidents based on campaign cluster pattern similarity
    
    Args:
        query_incident_id: Incident to find similar incidents for
        event_tags: Incident ID to campaign cluster pattern mapping
        k: Number of similar incidents to recommend
        quality_map: Cluster quality scores
        source_algo_map: Cluster algorithm sources
        cluster_sizes: Cluster ID to member count mapping
    
    Returns:
        DataFrame with similar incidents and evidence
    """
    if query_incident_id not in event_tags:
        return pd.DataFrame()
    
    query_tags = event_tags[query_incident_id]
    
    # Compute similarities
    recommendations = []
    for neighbor_id, neighbor_tags in event_tags.items():
        if neighbor_id == query_incident_id:
            continue
        
        score = jaccard_similarity(query_tags, neighbor_tags)
        if score > 0:
            intersection = query_tags & neighbor_tags
            recommendations.append({
                "query_incident_id": query_incident_id,
                "neighbor_incident_id": neighbor_id,
                "score_jaccard": score,
                "evidence_intersection": list(intersection),
                "num_intersecting_clusters": len(intersection)
            })
    
    # Sort by score (desc), then by neighbor_incident_id (asc) for stable tie-breaking
    recommendations.sort(key=lambda x: (-x["score_jaccard"], x["neighbor_incident_id"]))
    recommendations = recommendations[:k]
    
    # Attach evidence stats
    for rec in recommendations:
        evidence_stats = []
        for cluster_id in rec["evidence_intersection"]:
            evidence_stats.append({
                "cluster_id": int(cluster_id),
                "quality": float(quality_map.get(cluster_id, 0.0)),
                "member_count": int(cluster_sizes.get(cluster_id, 0)),
                "source_algo": str(source_algo_map.get(cluster_id, "UNKNOWN"))
            })
        # Sort evidence by quality (desc), then member_count (desc), then cluster_id (asc) for stable ordering
        evidence_stats.sort(key=lambda x: (-x["quality"], -x["member_count"], x["cluster_id"]))
        rec["evidence_stats"] = evidence_stats
    
    return pd.DataFrame(recommendations) if recommendations else pd.DataFrame()


def evaluate_recommender(
    event_tags_query: Dict[str, Set[int]],
    event_tags_labeled: Dict[str, Set[int]],
    gt_map: Dict[str, str],
    k: int,
    quality_map: Dict[int, float],
    source_algo_map: Dict[int, str],
    cluster_sizes: Dict[int, int]
) -> Dict[str, float]:
    """
    Evaluate recommender system using ground truth labels
    
    Args:
        event_tags_query: Query event tag sets
        event_tags_labeled: Labeled event tag sets
        gt_map: Event ID to ground truth actor mapping
        k: Number of recommendations to consider
        quality_map: Cluster quality scores
        source_algo_map: Cluster sources
        cluster_sizes: Cluster ID to member count mapping
    
    Returns:
        Dict with precision, completeness, and accuracy
    """
    precisions = []
    completeness_count = 0
    total_queries = 0
    
    for query_id in event_tags_query:
        if query_id not in gt_map:
            continue
        
        total_queries += 1
        query_actor = gt_map[query_id]
        
        # Get recommendations
        recs = recommend_top_k(query_id, event_tags_labeled, k, quality_map, source_algo_map, cluster_sizes)
        
        if len(recs) > 0:
            completeness_count += 1
            
            # Calculate precision: fraction with same actor
            correct = 0
            for _, row in recs.iterrows():
                neighbor_id = row["neighbor_incident_id"]
                if neighbor_id in gt_map and gt_map[neighbor_id] == query_actor:
                    correct += 1
            
            precision = correct / len(recs)
            precisions.append(precision)
        else:
            precisions.append(0.0)
    
    # Compute metrics
    if total_queries == 0:
        return {"top_k_precision": 0.0, "completeness": 0.0, "top_k_accuracy": 0.0}
    
    avg_precision = np.mean(precisions) if precisions else 0.0
    completeness = completeness_count / total_queries
    accuracy = avg_precision * completeness
    
    return {
        "top_k_precision": avg_precision,
        "completeness": completeness,
        "top_k_accuracy": accuracy,
        "total_queries": total_queries,
        "queries_with_recs": completeness_count
    }

