"""
Distance metrics for DNS domain record comparison

Implements multi-feature distance computation based on:
"Using DNS Patterns for Automated Cyber Threat Attribution" (Leite et al., 2024)
"""

import numpy as np
from typing import Set, Dict
from Levenshtein import distance as levenshtein_distance

from ..models.domain_record import DomainRecord


def lev_norm(a: str, b: str) -> float:
    """
    Normalized Levenshtein distance [0,1]
    
    Args:
        a: First string
        b: Second string
    
    Returns:
        Normalized Levenshtein distance in range [0, 1]
    """
    if a == b:
        return 0.0
    L = max(len(a or ""), len(b or ""))
    if L == 0:
        return 0.0
    return levenshtein_distance(a or "", b or "") / L


def jaccard_dist(A: Set[str], B: Set[str]) -> float:
    """
    Jaccard distance for sets [0,1]
    
    Args:
        A: First set
        B: Second set
    
    Returns:
        Jaccard distance: 1 - |A ∩ B| / |A ∪ B|
    """
    A = set(A or [])
    B = set(B or [])
    if not A and not B:
        return 0.0
    union_size = len(A | B)
    if union_size == 0:
        return 0.0
    return 1.0 - (len(A & B) / union_size)


def registrar_dist(x: DomainRecord, y: DomainRecord) -> float:
    """
    Registrar distance with IANA ID shortcut
    
    If both records have matching registrar_id, returns 0.
    Otherwise, computes normalized Levenshtein distance on registrar names.
    
    Args:
        x: First domain record
        y: Second domain record
    
    Returns:
        Distance between registrar fields [0, 1]
    """
    if x.registrar_id and y.registrar_id and x.registrar_id == y.registrar_id:
        return 0.0
    return lev_norm(x.registrar_name or "", y.registrar_name or "")


def asn_dist(x: DomainRecord, y: DomainRecord) -> float:
    """
    ASN distance with exact match shortcut
    
    If both records have matching ASN, returns 0.
    Otherwise, computes normalized Levenshtein distance on host organization names.
    
    Args:
        x: First domain record
        y: Second domain record
    
    Returns:
        Distance between ASN/host fields [0, 1]
    """
    if x.asn and y.asn and x.asn == y.asn:
        return 0.0
    return lev_norm(x.host_org or "", y.host_org or "")


def compute_pair_distance(a: DomainRecord, b: DomainRecord, config: Dict) -> float:
    """
    Compute weighted distance between two records
    
    Implements Equation 1 from [Leite 2024] with configurable feature weights.
    
    Features (in order):
    1. Domain (Levenshtein)
    2. Subdomains (Jaccard)
    3. Email user (Levenshtein)
    4. Registrar (IANA ID aware)
    5. ASN (exact match aware)
    
    Args:
        a: First domain record
        b: Second domain record
        config: Configuration dict with 'weights' and 'missing_feature_mode'
    
    Returns:
        Weighted distance in range [0, 1]
    """
    weights = config["weights"]
    mode = config["missing_feature_mode"]

    # Compute feature distances
    distances = [
        lev_norm(a.domain, b.domain),           # 1. Domain
        jaccard_dist(a.subdomains, b.subdomains),  # 2. Subdomains
        lev_norm(a.email_user, b.email_user),   # 3. Email
        registrar_dist(a, b),                   # 4. Registrar
        asn_dist(a, b)                          # 5. ASN
    ]

    # Check for missing features
    missing_mask = [
        False,  # Domain always present
        len(a.subdomains) == 0 and len(b.subdomains) == 0,  # Subdomains
        not a.email_user and not b.email_user,  # Email
        not a.registrar_name and not b.registrar_name,  # Registrar
        not a.host_org and not b.host_org  # ASN
    ]

    if mode == "drop_dim":
        # Remove missing dimensions
        valid_indices = [i for i, missing in enumerate(missing_mask) if not missing]
        if not valid_indices:
            # Fallback if all missing
            return np.mean(distances)
        num = sum(weights[i] * distances[i] for i in valid_indices)
        denom = sum(weights[i] for i in valid_indices)
        return num / denom if denom > 0 else np.mean(distances)

    elif mode == "penalize":
        # Assign distance=1.0 for missing features
        adjusted_distances = [
            1.0 if missing else dist
            for dist, missing in zip(distances, missing_mask)
        ]
        num = sum(w * d for w, d in zip(weights, adjusted_distances))
        denom = sum(weights)
        return num / denom if denom > 0 else np.mean(adjusted_distances)

    else:
        raise ValueError(f"Unknown missing_feature_mode: {mode}")

