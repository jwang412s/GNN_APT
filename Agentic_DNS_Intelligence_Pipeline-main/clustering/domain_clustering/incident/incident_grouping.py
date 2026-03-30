"""
Infrastructure-based incident grouping

Implements functions for grouping domain records into incidents based on
shared infrastructure (registrar_id + ASN) following [Leite 2024, Section 5.4.3].
"""

import numpy as np
from typing import Dict, List, Any, Optional
import re

from ..models import DomainRecord
from ..models.domain_record import _normalize_identifier_value


def compute_infrastructure_signature(registrar_id: Optional[str], asn: Optional[str]) -> str:
    """
    Generate a normalized infrastructure signature from registrar and ASN.
    
    Args:
        registrar_id: Registrar identifier or None.
        asn: Autonomous System Number or None.
    
    Returns:
        Normalized signature string such as "1928|AS12345".
    
    Examples:
        >>> compute_infrastructure_signature("1928", "AS12345")
        '1928|AS12345'
        >>> compute_infrastructure_signature("NAMECHEAP", "AWS")
        'AWS|NAMECHEAP'
        >>> compute_infrastructure_signature(None, "AS12345")
        'AS12345|UNKNOWN'
    """
    registrar_id = str(registrar_id) if registrar_id else "UNKNOWN"
    asn = str(asn) if asn else "UNKNOWN"
    features = sorted([registrar_id, asn])
    signature = "|".join(features)
    return signature


# Global debug counter (compatible with legacy code)
INFRA_ASSIGN_DEBUG_COUNT = 0


def assign_infrastructure_incident_id(
    registrar_id: Optional[str],
    asn: Optional[str],
    config: Optional[Dict] = None
) -> str:
    """
    Assign an infrastructure-based incident_id using registrar and ASN.
    
    Args:
        registrar_id: Registrar identifier or None.
        asn: Autonomous System Number or None.
        config: Configuration dict (for debug limits)
    
    Returns:
        Incident identifier such as "infra_1928|AS12345".
    
    Examples:
        >>> assign_infrastructure_incident_id("1928", "AS12345")
        'infra_1928|AS12345'
        >>> assign_infrastructure_incident_id("1", "AS8452")
        'infra_1|AS8452'
        >>> assign_infrastructure_incident_id(None, None)
        'infra_UNKNOWN|UNKNOWN'
    """
    global INFRA_ASSIGN_DEBUG_COUNT
    
    if config:
        debug_limit = config.get("infra_debug_assign_limit", 0)
        if debug_limit > 0 and INFRA_ASSIGN_DEBUG_COUNT < debug_limit:
            print("DEBUG assign_infrastructure_incident_id:")
            print(f"  registrar_id: {registrar_id} (type: {type(registrar_id)})")
            print(f"  asn: {asn} (type: {type(asn)})")
            INFRA_ASSIGN_DEBUG_COUNT += 1
    
    signature = compute_infrastructure_signature(registrar_id, asn)
    incident_id = f"infra_{signature}"
    return incident_id


def build_incidents_from_infrastructure(
    records: List[DomainRecord],
    final_labels: np.ndarray
) -> Dict[str, Dict[str, Any]]:
    """
    Group records into incidents by shared infrastructure (registrar_id + ASN)
    following the infrastructure-centric strategy in [Leite 2024, Section 5.4.3].
    
    Args:
        records: Sanitized domain records with normalized registrar_id and ASN.
        final_labels: Cluster labels from the combined DBSCAN/HDBSCAN pipeline.
    
    Returns:
        Dict mapping incident_id to metadata dict including domains and cluster patterns.
    """
    incidents: Dict[str, Dict[str, Any]] = {}
    
    for record, label in zip(records, final_labels):
        if label == -1:
            continue
        
        incident_id = assign_infrastructure_incident_id(record.registrar_id, record.asn)
        
        if incident_id not in incidents:
            incidents[incident_id] = {
                "incident_id": incident_id,
                "registrar_id": record.registrar_id,
                "asn": record.asn,
                "domains": [],
                "pattern_set": set(),
                "time_range": None
            }
        
        info = incidents[incident_id]
        info["domains"].append(record.domain)
        info["pattern_set"].add(int(label))
    
    for info in incidents.values():
        pattern_list = sorted(int(cid) for cid in info["pattern_set"])
        info["pattern_set"] = pattern_list
        info["domain_count"] = len(info["domains"])
        info["cluster_count"] = len(pattern_list)
    
    print(f"✓ Built {len(incidents)} incidents from infrastructure grouping")
    return incidents

