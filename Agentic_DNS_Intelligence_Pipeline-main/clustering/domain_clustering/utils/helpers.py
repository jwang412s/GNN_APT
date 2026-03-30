"""
Shared utility functions

Common helper functions used across multiple modules.
"""

import re
import pandas as pd
import numpy as np
from datetime import timezone
from typing import Optional, Dict, Any

from ..models.domain_record import _normalize_identifier_value
from ..incident.incident_grouping import assign_infrastructure_incident_id


def sanitize_token(s: str) -> str:
    """
    Sanitize string for use in identifiers
    
    Args:
        s: Input string
    
    Returns:
        Sanitized string safe for use in identifiers
    """
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def normalize_date(val: Any) -> Optional[pd.Timestamp]:
    """
    Normalize value to UTC timestamp
    
    Args:
        val: Input value (datetime, string, etc.)
    
    Returns:
        UTC timestamp or None if invalid
    """
    if pd.isna(val):
        return None
    ts = pd.to_datetime(val, utc=True, errors="coerce")
    return ts if pd.notna(ts) else None


def pick_ts(row: pd.Series, policy: Dict) -> pd.Timestamp:
    """
    Pick timestamp from row based on policy
    
    Args:
        row: DataFrame row
        policy: Timestamp policy dict with 'prefer' list of column names
    
    Returns:
        Timestamp from preferred columns or current UTC time as fallback
    """
    for col in policy["prefer"]:
        if col in row and pd.notna(row[col]):
            ts = normalize_date(row[col])
            if ts is not None:
                return ts
    return pd.Timestamp.now(tz=timezone.utc)


def naive_root(domain: str) -> str:
    """
    Extract registrable root (approximation without external deps)
    
    Args:
        domain: Domain name
    
    Returns:
        Root domain (e.g., "example.com" from "www.example.com")
    """
    parts = (domain or "").lower().strip(".").split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return sanitize_token(domain or "unknown")


def build_incident_id(
    row: pd.Series,
    policy: Dict,
    ts_utc: pd.Timestamp,
    config: Optional[Dict] = None
) -> str:
    """
    Build deterministic incident_id from row
    
    Supports multiple strategies:
    - infrastructure_hash: Based on registrar_id + ASN
    - use_columns: Based on specified columns + date
    - fallback: Uses row index
    
    Args:
        row: DataFrame row
        policy: Incident ID policy dict
        ts_utc: Timestamp for date-based strategies
        config: Configuration dict (optional, for debug limits)
    
    Returns:
        Incident ID string
    """
    strategy = policy.get("strategy", "infrastructure_hash")
    
    if strategy == "infrastructure_hash":
        registrar_id = _normalize_identifier_value(row.get("registrar_id")) \
            or _normalize_identifier_value(row.get("registrar"))
        asn_value = _normalize_identifier_value(row.get("asn"))
        if not asn_value:
            host_provider_val = row.get("host_provider", "")
            host_provider_raw = "" if pd.isna(host_provider_val) else str(host_provider_val).strip()
            match = re.search(r"\bAS(\d+)\b", host_provider_raw)
            if match:
                asn_value = match.group(1)
        return assign_infrastructure_incident_id(registrar_id, asn_value, config)
    
    date_fmt = policy.get("date_fmt", "%Y%m%d")
    date_str = ts_utc.strftime(date_fmt)
    
    if strategy == "use_columns":
        cols = policy.get("columns", [])
        tokens = []
        for c in cols:
            if c in row and pd.notna(row[c]):
                tokens.append(sanitize_token(str(row[c])))
        if tokens:
            date_fmt = policy.get("date_fmt", "%Y%m%d")
            date_str = ts_utc.strftime(date_fmt)
            return "_".join(tokens + [date_str])
    
    # Fallback uses sanitized row index to avoid collisions
    return f"row_{row.name}"

