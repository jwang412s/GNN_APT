# cluster_unknown_dns.py

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN

UNKNOWN_ENRICHED = "enriched_domains_hq_dns.csv"
UNKNOWN_CLUSTERED = "unknown_domains_dns_clustered.csv"
UNKNOWN_SUMMARY = "unknown_clusters_dns_summary.csv"

# Candidate features to use if present
FEATURE_CANDIDATES = [
    "asn",
    "registrar",
    "ns_base",
    "mx_base",
    "soa_email",
    "ip_count",
    "host_provider",  # optional, used if present
]


def build_feature_matrix(df, feature_cols):
    """
    Build a pairwise distance matrix based on how many categorical
    features match between two domains.

    similarity(i,j) = (# matching features) / k
    distance = 1 - similarity
    """
    feats = df[feature_cols].fillna("MISSING").astype(str).values
    n, k = feats.shape

    sim = np.zeros((n, n), dtype=float)
    for i in range(n):
        sim[i, i] = 1.0
        for j in range(i + 1, n):
            matches = np.sum(feats[i] == feats[j])
            s = matches / float(k)
            sim[i, j] = s
            sim[j, i] = s

    dist = 1.0 - sim
    return dist


def main():
    print(f"[*] Loading unknown enriched domains from {UNKNOWN_ENRICHED} ...")
    df = pd.read_csv(UNKNOWN_ENRICHED)

    # Select features that actually exist in the file
    feature_cols = [c for c in FEATURE_CANDIDATES if c in df.columns]
    if not feature_cols:
        raise ValueError(
            f"No expected feature columns found. Available columns: {list(df.columns)}"
        )

    print(f"[*] Using feature columns: {feature_cols}")

    # Build distance matrix
    print("[*] Building distance matrix (may take a bit for large N)...")
    dist = build_feature_matrix(df, feature_cols)

    # Run DBSCAN on precomputed distances
    print("[*] Running DBSCAN on precomputed distance matrix...")
    clustering = DBSCAN(
        eps=0.5,
        min_samples=2,
        metric="precomputed",
    ).fit(dist)

    # Build output DF with domain + features + cluster_id
    df_out = df[["domain"] + feature_cols].copy()
    df_out["cluster_id"] = clustering.labels_
    df_out.to_csv(UNKNOWN_CLUSTERED, index=False)
    print(f"[+] Saved clustered unknown domains to {UNKNOWN_CLUSTERED}")

    # Build simple summary
    summary = (
        df_out.groupby("cluster_id")
        .agg(
            count=("domain", "count"),
            sample_domains=("domain", lambda x: "; ".join(x.head(5).astype(str))),
        )
        .reset_index()
        .sort_values(by="count", ascending=False)
    )

    summary.to_csv(UNKNOWN_SUMMARY, index=False)
    print(f"[+] Saved unknown cluster summary to {UNKNOWN_SUMMARY}")


if __name__ == "__main__":
    main()
