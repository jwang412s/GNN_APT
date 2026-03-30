"""
Incident data structures

Implements the Incident dataclass for representing DNS campaign incidents
grouped by infrastructure (registrar_id + ASN).
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Incident:
    """
    Represents a DNS campaign incident grouped by infrastructure
    
    Attributes:
        incident_id: Infrastructure-based incident identifier
        registrar_id: Optional registrar identifier
        asn: Optional ASN identifier
        domains: List of domain names in this incident
        pattern_set: Sorted list of cluster IDs (campaign cluster pattern)
        domain_count: Number of domains in this incident
        cluster_count: Number of distinct clusters in pattern_set
        time_range: Optional time range string (start-end dates)
    """
    incident_id: str
    registrar_id: Optional[str]
    asn: Optional[str]
    domains: List[str]
    pattern_set: List[int]  # sorted list of cluster IDs
    domain_count: int
    cluster_count: int
    time_range: Optional[str] = None

