"""
Data loading and preprocessing utilities

Handles loading enriched datasets, time window filtering, and record normalization.
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timezone, timedelta
from typing import Optional, Any, Dict

from ..models import DomainRecord
from ..models.domain_record import _normalize_identifier_value, sanitize_token, normalize_date, pick_ts
from ..incident.incident_grouping import assign_infrastructure_incident_id


def load_data(path: str) -> pd.DataFrame:
    """
    Load enriched dataset from CSV or Parquet
    
    Args:
        path: Path to CSV or Parquet file
    
    Returns:
        DataFrame with loaded data
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    
    # Normalize key identifier columns to string early to avoid float artifacts
    for col in ["registrar", "registrar_id", "asn", "host_provider"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: _normalize_identifier_value(v) or "")
    
    print(f"✓ Loaded {len(df)} records from {path}")
    return df


def apply_time_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """
    Filter to records within time window
    
    Args:
        df: Input DataFrame
        days: Number of days in the time window
    
    Returns:
        Filtered DataFrame
    """
    if "ts" not in df.columns:
        print("⚠ No 'ts' column, skipping time window filter")
        return df
    
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    cutoff = pd.Timestamp.now(tz=timezone.utc) - timedelta(days=days)
    df_filtered = df[df["ts"] >= cutoff].copy()
    
    print(f"✓ Time window filter ({days} days): {len(df)} → {len(df_filtered)} records")
    return df_filtered


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
        config: Configuration dict (for debug limits, optional)
    
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


def ensure_event_fields(df: pd.DataFrame, config: Optional[Dict] = None) -> pd.DataFrame:
    """
    Ensure every row has ts and incident_id fields
    
    Args:
        df: Input DataFrame
        config: Configuration dict (defaults to CONFIG)
    
    Returns:
        DataFrame with ts and incident_id fields populated
    """
    if config is None:
        from ..config import CONFIG
        config = CONFIG
    
    # Handle ts
    if "ts" not in df.columns:
        df["ts"] = df.apply(lambda r: pick_ts(r, config["timestamp_policy"]), axis=1)
    else:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce") \
                     .fillna(pd.Timestamp.now(tz=timezone.utc))
    
    # Handle incident_id
    if "incident_id" not in df.columns:
        df["incident_id"] = df.apply(
            lambda r: build_incident_id(r, config["incident_id_policy"], r["ts"], config), axis=1
        )
    else:
        df["incident_id"] = df["incident_id"].astype(str).map(sanitize_token)
    
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df


def sanitize_record(row: pd.Series, config: Dict) -> DomainRecord:
    """
    Normalize and sanitize a single record
    
    Args:
        row: DataFrame row
        config: Configuration dict
    
    Returns:
        DomainRecord object
    """
    # Domain
    domain = str(row.get("domain", "")).lower().strip().rstrip(".")
    
    # Subdomains
    subdomains_raw = row.get("subdomains", "")
    if isinstance(subdomains_raw, str):
        subdomains = set(s.strip().lower() for s in subdomains_raw.split(config["subdomain_sep"]) if s.strip())
    elif isinstance(subdomains_raw, (list, set)):
        subdomains = set(str(s).strip().lower() for s in subdomains_raw if str(s).strip())
    else:
        subdomains = set()
    
    # Email user
    email = row.get("email_user", "") or row.get("email", "")
    email_str = str(email).strip()
    if "@" in email_str:
        email_user = email_str.split("@")[0].lower()
    else:
        email_user = email_str.lower() if email_str and email_str.lower() != "unknown" else ""
    
    # Registrar with IANA ID extraction
    registrar_raw = row.get("registrar", "")
    registrar_clean = "" if pd.isna(registrar_raw) else str(registrar_raw).strip()
    registrar_id_match = re.search(r"\(ID(\d+)\)", registrar_clean)
    registrar_id = None
    registrar_name = registrar_clean
    
    if registrar_id_match:
        registrar_id = registrar_id_match.group(1)
        registrar_name = re.sub(r"\s*\(ID\d+\)", "", registrar_clean).strip()
    else:
        registrar_id_column = _normalize_identifier_value(row.get("registrar_id"))
        if registrar_id_column:
            registrar_id = registrar_id_column
        elif registrar_name:
            registrar_id = registrar_name
    
    # Host provider with ASN extraction
    host_provider_val = row.get("host_provider", "")
    host_provider_raw = "" if pd.isna(host_provider_val) else str(host_provider_val).strip()
    m = re.search(r"\bAS(\d+)\b", host_provider_raw)
    asn_value = _normalize_identifier_value(row.get("asn"))
    
    if asn_value:
        asn = asn_value
    elif m:
        asn = m.group(1)
    else:
        asn = None
    
    if m:
        host_org = re.sub(r"^\s*AS\d+\s*[-:,]?\s*", "", host_provider_raw).strip()
    else:
        host_org = host_provider_raw
    
    # Event metadata
    incident_id = str(row.get("incident_id", "unknown"))
    ts = row.get("ts", pd.Timestamp.now(tz=timezone.utc))
    if not isinstance(ts, pd.Timestamp):
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
    if pd.isna(ts):
        ts = pd.Timestamp.now(tz=timezone.utc)
    
    return DomainRecord(
        domain=domain,
        subdomains=subdomains,
        email_user=email_user,
        registrar_name=registrar_name,
        registrar_id=registrar_id,
        host_org=host_org,
        asn=asn,
        incident_id=incident_id,
        ts=ts,
        index=row.name
    )

