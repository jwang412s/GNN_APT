#!/usr/bin/env python
import pandas as pd
import numpy as np

# -------------------------------------------------
# Config
# -------------------------------------------------
UNKNOWN_CLUSTERED_CSV = "unknown_domains_dns_clustered.csv"
KNOWN_CLUSTERED_CSV   = "known_actors_dns_clustered.csv"
OUTPUT_CSV            = "cluster_attribution_candidates_dns.csv"

# Candidate features we *try* to use. We will pick the subset
# that actually exists in BOTH known and unknown CSVs.
FEATURE_CANDIDATES = [
    "asn",
    "registrar",
    "ns_base",
    "mx_base",
    "soa_email",
    "ip_count",  # treated as small numeric / bucket
]

# Feature weights (higher = more important)
FEATURE_WEIGHTS = {
    "asn":       3.0,
    "ns_base":   3.0,
    "soa_email": 3.0,
    "mx_base":   2.0,
    "registrar": 1.0,
    "ip_count":  1.0,
}

# Confidence thresholds (can tune later)
MIN_CONFIDENCE = 0.30  # 30%


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def normalize_value(val):
    """Normalize a single cell value to a string or None."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def split_multi(val):
    """Split comma-separated string into a set of lowercase tokens."""
    if val is None:
        return set()
    parts = [p.strip().lower() for p in str(val).split(",") if p.strip()]
    return set(parts)


def ip_count_bucket(val):
    """Bucket numeric ip_count into coarse groups."""
    try:
        v = int(val)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return "0"
    elif v == 1:
        return "1"
    elif 2 <= v <= 3:
        return "2-3"
    elif 4 <= v <= 8:
        return "4-8"
    else:
        return "9+"


def build_cluster_feature_sets(df, cluster_col, feature_cols):
    """
    Build:
      - cluster_features: dict[cluster_id][feature] -> set(values)
      - cluster_actor:    dict[cluster_id] -> actor label for known set
    """
    cluster_features = {}
    cluster_actor = {}

    has_actor_label = "actor_label" in df.columns
    has_actor_raw   = "actor" in df.columns

    for _, row in df.iterrows():
        cid = row[cluster_col]
        if cid not in cluster_features:
            cluster_features[cid] = {f: set() for f in feature_cols}

        # Attach an actor label for known clusters
        if has_actor_label:
            if cid not in cluster_actor:
                cluster_actor[cid] = str(row["actor_label"])
        elif has_actor_raw:
            if cid not in cluster_actor:
                # first actor we see for this cluster
                cluster_actor[cid] = str(row["actor"])

        # Add feature values
        for f in feature_cols:
            raw = normalize_value(row.get(f))

            if f == "ip_count":
                bucket = ip_count_bucket(raw)
                if bucket is not None:
                    cluster_features[cid][f].add(bucket)
                continue

            vals = split_multi(raw)
            cluster_features[cid][f].update(vals)

    # if no actor columns at all, cluster_actor will just stay empty
    return cluster_features, cluster_actor



def per_feature_jaccard(set_a, set_b):
    """Jaccard similarity for two sets."""
    if not set_a and not set_b:
        return None
    union = set_a | set_b
    if not union:
        return None
    inter = set_a & set_b
    return len(inter) / len(union)


def compute_weighted_similarity(cluster_u, cluster_k, feature_cols, weights):
    """
    Compute weighted similarity & evidence count for two clusters.

    Returns:
      weighted_sim (0..1),
      base_sim (unweighted mean),
      evidence_features (features with sim > 0)
    """
    num = 0.0
    den = 0.0
    sims = []
    evidence_features = 0

    for f in feature_cols:
        w = weights.get(f, 1.0)
        set_u = cluster_u.get(f, set())
        set_k = cluster_k.get(f, set())

        sim = per_feature_jaccard(set_u, set_k)
        if sim is None:
            continue

        sims.append(sim)
        den += w
        num += w * sim

        if sim > 0:
            evidence_features += 1

    if den == 0 or not sims:
        return 0.0, 0.0, 0

    weighted_sim = num / den
    base_sim = float(np.mean(sims))
    return weighted_sim, base_sim, evidence_features


# -------------------------------------------------
# Main
# -------------------------------------------------

def main():
    print("[*] Loading clustered datasets...")

    df_unknown = pd.read_csv(UNKNOWN_CLUSTERED_CSV)
    df_known   = pd.read_csv(KNOWN_CLUSTERED_CSV)

    # Dynamically pick only the features that exist in BOTH dataframes
    available_features = [
        c for c in FEATURE_CANDIDATES
        if (c in df_unknown.columns) and (c in df_known.columns)
    ]
    if not available_features:
        raise ValueError(
            f"No common feature columns found between unknown and known. "
            f"Unknown cols: {list(df_unknown.columns)}, "
            f"Known cols: {list(df_known.columns)}"
        )

    print(f"[*] Using feature columns: {available_features}")

    # Figure out what the cluster column is called in each file
    unknown_cluster_col = "cluster_id"
    if unknown_cluster_col not in df_unknown.columns:
        raise ValueError(f"'cluster_id' not found in {UNKNOWN_CLUSTERED_CSV}")

    if "known_cluster_id" in df_known.columns:
        known_cluster_col = "known_cluster_id"
    elif "cluster_id" in df_known.columns:
        known_cluster_col = "cluster_id"
    else:
        raise ValueError(
            f"Neither 'known_cluster_id' nor 'cluster_id' found in {KNOWN_CLUSTERED_CSV}. "
            f"Columns: {list(df_known.columns)}"
        )

    unknown_features, _          = build_cluster_feature_sets(
        df_unknown, cluster_col=unknown_cluster_col, feature_cols=available_features
    )
    known_features, known_actors = build_cluster_feature_sets(
        df_known, cluster_col=known_cluster_col, feature_cols=available_features
    )

    rows = []

    print("[*] Computing weighted similarities...")
    for u_cid, u_feats in unknown_features.items():
        for k_cid, k_feats in known_features.items():
            actor = known_actors.get(k_cid, "Unknown")

            weighted_sim, base_sim, evidence = compute_weighted_similarity(
                u_feats, k_feats, available_features, FEATURE_WEIGHTS
            )

            confidence_0_1 = weighted_sim
            confidence_percent = round(confidence_0_1 * 100.0, 1)

            decision = (
                "Attributed"
                if confidence_0_1 >= MIN_CONFIDENCE
                else "Unknown/Low-confidence"
            )

            rows.append(
                {
                    "unknown_cluster_id": u_cid,
                    "known_cluster_id":   k_cid,
                    "actor_label":        actor,
                    "weighted_similarity":weighted_sim,
                    "base_similarity":    base_sim,
                    "evidence_features":  evidence,
                    "confidence_0_1":     confidence_0_1,
                    "confidence_percent": confidence_percent,
                    "decision":           decision,
                }
            )

    df_attr = pd.DataFrame(rows)
    df_attr.sort_values(
        by=["unknown_cluster_id", "confidence_0_1"],
        ascending=[True, False],
        inplace=True,
    )

    df_attr.to_csv(OUTPUT_CSV, index=False)
    print(f"[+] Saved attribution candidates to {OUTPUT_CSV}")
    print(df_attr.head())


if __name__ == "__main__":
    main()
