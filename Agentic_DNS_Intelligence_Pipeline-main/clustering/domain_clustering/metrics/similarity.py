"""
Similarity metrics for incident pattern comparison

Implements Jaccard similarity for campaign cluster pattern comparison.
"""

from typing import Set


def jaccard_similarity(set_a: Set[int], set_b: Set[int]) -> float:
    """
    Compute Jaccard similarity between two sets
    
    Jaccard similarity = |A ∩ B| / |A ∪ B|
    
    Args:
        set_a: First set of cluster IDs
        set_b: Second set of cluster IDs
    
    Returns:
        Jaccard similarity in range [0, 1]
    """
    if not set_a and not set_b:
        return 0.0
    union_size = len(set_a | set_b)
    if union_size == 0:
        return 0.0
    return len(set_a & set_b) / union_size

