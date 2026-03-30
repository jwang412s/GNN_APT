# cluster_known_dns.py

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN

KNOWN_COMBINED = "known_actors_dns_combined.csv"
KNOWN_CLUSTERED = "known_actors_dns_with_clusters.csv"
KNOWN_SUMMARY = "known_actor_dns_clusters_summary.csv"

FEATURE_CANDIDATES = [
    'asn',
    'registrar',
    'ns_base',
    'mx_base',
    'soa_email',
    'ip_count',
    'host_provider',   # NEW
]

def build_feature_matrix(df, feature_cols):
    df_feats = df[feature_cols].fillna("MISSING").astype(str).values
    n, k = df_feats.shape
    sim = np.zeros((n, n), dtype=float)

    for i in range(n):
        sim[i, i] = 1.0
        for j in range(i + 1, n):
            matches = np.sum(df_feats[i] == df_feats[j])
            s = matches / float(k)
            sim[i, j] = s
            sim[j, i] = s

    dist = 1.0 - sim
    return dist

def main():
    print(f"[*] Loading known-actor DNS combined data from {KNOWN_COMBINED} ...")
    df = pd.read_csv(KNOWN_COMBINED)

    # Ensure we have actor and domain columns
    if "actor" not in df.columns:
        raise ValueError(f"'actor' column not found. Columns: {list(df.columns)}")
    if "domain" not in df.columns:
        raise ValueError(f"'domain' column not found. Columns: {list(df.columns)}")

    feature_cols = [c for c in FEATURE_CANDIDATES if c in df.columns]
    if not feature_cols:
        raise ValueError(f"No expected feature columns found. "
                         f"Available columns: {list(df.columns)}")

    print(f"[*] Using feature columns: {feature_cols}")
    print("[*] Building distance matrix...")
    dist = build_feature_matrix(df, feature_cols)

    print("[*] Running DBSCAN on precomputed distance matrix...")
    clustering = DBSCAN(
        eps=0.5,
        min_samples=2,
        metric="precomputed"
    ).fit(dist)

    df["known_cluster_id"] = clustering.labels_
    df.to_csv(KNOWN_CLUSTERED, index=False)
    print(f"[+] Saved clustered known-actor domains to {KNOWN_CLUSTERED}")

    summary = (
        df.groupby("known_cluster_id")
        .agg(
            count=("domain", "count"),
            actors=("actor", lambda x: ", ".join(sorted(set(x)))),
            sample_domains=("domain", lambda x: "; ".join(x.head(5).astype(str)))
        )
        .reset_index()
        .sort_values(by="count", ascending=False)
    )

    summary.to_csv(KNOWN_SUMMARY, index=False)
    print(f"[+] Saved known-actor cluster summary to {KNOWN_SUMMARY}")

if __name__ == "__main__":
    main()
