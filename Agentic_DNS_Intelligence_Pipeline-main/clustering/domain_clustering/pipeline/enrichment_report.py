"""
Enrichment quality report utilities

Builds and analyzes enrichment quality reports from normalized data.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional

from ..config import CONFIG


def build_enrichment_report(
    df_norm: pd.DataFrame,
    config: Optional[Dict] = None
) -> dict:
    """
    Build enrichment quality report from normalized data
    
    Args:
        df_norm: Normalized DataFrame
        config: Configuration dict (defaults to CONFIG)
    
    Returns:
        Dict with enrichment quality metrics and recommendations
    """
    if config is None:
        config = CONFIG
    
    total = len(df_norm)
    
    def present_rate(col, pred):
        """Calculate presence rate for a column, handling missing columns"""
        if col not in df_norm.columns:
            return 0.0
        return float((df_norm[col].map(pred)).sum()) / max(1, total)
    
    # Check for column name variations (registrar vs registrar_name)
    registrar_col = "registrar" if "registrar" in df_norm.columns else "registrar_name"
    
    rates = {
        "subdomains_present": present_rate("subdomains", lambda v: isinstance(v, (set, list, str)) and len(v) > 0),
        "email_present": present_rate("email_user", lambda v: isinstance(v, str) and len(v) > 0 and v not in ["abuse", "UNKNOWN"]),
        "registrar_present": present_rate(registrar_col, lambda v: isinstance(v, str) and len(v) > 0 and v != "UNKNOWN"),
        "asn_present": present_rate("asn", lambda v: isinstance(v, str) and len(v) > 0 and v not in ["0", "UNKNOWN"])
    }
    overall = float(np.mean([rates["subdomains_present"], rates["email_present"], rates["registrar_present"], rates["asn_present"]]))
    
    warnings = []
    recs = []
    th = config["enrichment_report"]
    if rates["subdomains_present"] < (1.0 - th["warn_subdomain_missing_gt"]):
        warnings.append("Subdomains high miss rate may reduce precision")
        recs.append("Consider preset conservative")
    if rates["email_present"] < (1.0 - th["warn_email_missing_gt"]):
        warnings.append("Email often absent or abuse")
        recs.append("Reduce email weight to 0.2")
    if rates["registrar_present"] < (1.0 - th["warn_registrar_missing_gt"]):
        warnings.append("Registrar frequently missing")
        recs.append("Emphasize ASN and domain morphology")
    
    return {
        "total_records": int(total),
        "present_rates": rates,
        "overall_quality": overall,
        "warnings": warnings,
        "recommendations": sorted(set(recs))
    }


def suggest_preset_from_enrichment(rep: dict):
    """
    Log preset suggestions based on enrichment report
    
    Args:
        rep: Enrichment report dict
    """
    recs = rep.get("recommendations", [])
    if "Reduce email weight to 0.2" in recs:
        print("Hint: try preset 'conservative' for low email presence")
    if "Consider preset conservative" in recs:
        print("Hint: preset 'conservative' can improve robustness under sparse subdomains")

