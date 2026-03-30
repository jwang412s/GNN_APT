"""
Campaign cluster pattern extraction

Extracts incident-level cluster patterns from clustering results.
"""

import numpy as np
from typing import Dict, Set, List

from ..models import DomainRecord


def build_incident_tag_sets(
    final_labels: np.ndarray,
    records: List[DomainRecord]
) -> Dict[str, Set[int]]:
    """
    Build incident-level campaign cluster patterns from cluster assignments
    
    Args:
        final_labels: Cluster labels for each record
        records: List of domain records
    
    Returns:
        Dict mapping incident_id to set of cluster IDs (campaign cluster pattern)
    """
    incident_tags = {}
    
    for label, record in zip(final_labels, records):
        if label == -1:
            continue  # Skip noise
        
        incident_id = record.incident_id
        if incident_id not in incident_tags:
            incident_tags[incident_id] = set()
        incident_tags[incident_id].add(int(label))
    
    print(f"✓ Built campaign cluster patterns for {len(incident_tags)} incidents")
    return incident_tags


# Backward compatibility wrapper
def build_event_tag_sets(
    final_labels: np.ndarray,
    records: List[DomainRecord]
) -> Dict[str, Set[int]]:
    """
    Backward compatibility wrapper for build_incident_tag_sets
    
    Args:
        final_labels: Cluster labels for each record
        records: List of domain records
    
    Returns:
        Dict mapping incident_id to set of cluster IDs (campaign cluster pattern)
    """
    return build_incident_tag_sets(final_labels, records)

