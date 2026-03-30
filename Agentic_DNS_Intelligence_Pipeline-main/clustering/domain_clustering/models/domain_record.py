"""
Domain record data structures and normalization utilities

Implements the DomainRecord dataclass and helper functions for data cleaning
and normalization based on the DNS threat intelligence pipeline.
"""

import re
import numpy as np
import pandas as pd
from datetime import timezone
from typing import Set, Optional, Any
from dataclasses import dataclass


@dataclass
class DomainRecord:
    """
    Normalized domain record with standardized fields
    
    Attributes:
        domain: Normalized domain name (lowercase, stripped)
        subdomains: Set of subdomain strings
        email_user: Email username part (before @)
        registrar_name: Registrar organization name
        registrar_id: Optional registrar IANA ID or normalized identifier
        host_org: Host provider organization name
        asn: Optional ASN identifier
        incident_id: Incident identifier (infrastructure-based)
        ts: Timestamp (UTC timezone)
        index: Original row index in source DataFrame
    """
    domain: str
    subdomains: Set[str]
    email_user: str
    registrar_name: str
    registrar_id: Optional[str]
    host_org: str
    asn: Optional[str]
    incident_id: str
    ts: pd.Timestamp
    index: int  # Original row index


def sanitize_token(s: str) -> str:
    """
    Sanitize string for use in identifiers
    
    Removes special characters and normalizes to lowercase alphanumeric
    with underscores, dots, and hyphens allowed.
    
    Args:
        s: Input string to sanitize
    
    Returns:
        Sanitized string, or "unknown" if input is empty/invalid
    """
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def normalize_date(val: Any) -> Optional[pd.Timestamp]:
    """
    Normalize value to UTC timestamp
    
    Args:
        val: Value to normalize (string, timestamp, or None)
    
    Returns:
        Timestamp in UTC timezone, or None if conversion fails
    """
    if pd.isna(val):
        return None
    ts = pd.to_datetime(val, utc=True, errors="coerce")
    return ts if pd.notna(ts) else None


def pick_ts(row: pd.Series, policy: dict) -> pd.Timestamp:
    """
    Pick timestamp from row based on policy preference order
    
    Args:
        row: DataFrame row with timestamp columns
        policy: Policy dict with "prefer" list of column names
    
    Returns:
        First available timestamp from preferred columns, or current UTC time
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
    
    Takes the last two domain parts as the root domain.
    
    Args:
        domain: Full domain name
    
    Returns:
        Root domain (e.g., "example.com" from "sub.example.com")
    """
    parts = (domain or "").lower().strip(".").split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return sanitize_token(domain or "unknown")


def _normalize_identifier_value(value: Any) -> Optional[str]:
    """
    Normalize numeric/object values into clean string identifiers
    
    Handles various input types (strings, integers, floats, NaN) and converts
    them to normalized string representations suitable for identifiers.
    
    Args:
        value: Value to normalize (can be str, int, float, None, or NaN)
    
    Returns:
        Normalized string identifier, or None if value is empty/invalid
    """
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return None
        try:
            float_val = float(s)
            if float_val.is_integer():
                return str(int(float_val))
        except ValueError:
            return s
        return s
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        if np.isnan(value):
            return None
        return str(int(value)) if value.is_integer() else str(value)
    s = str(value).strip()
    if not s:
        return None
    return s

