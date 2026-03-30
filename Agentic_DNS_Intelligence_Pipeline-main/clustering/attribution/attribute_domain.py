# attribute_domain.py
#
# Usage:
#   python attribute_domain.py microsfot.org updatemicfosoft.com ...
#
# This script:
#   1. Loads clustered unknown domains (DNS-enriched).
#   2. Loads cluster-level attribution candidates.
#   3. For each input domain, finds its cluster and prints
#      the top actor + confidence and other candidate actors.

import sys
import pandas as pd

# ======= FILE NAMES (change here if yours differ) =======

# Unknown domains clustered with DNS features (from cluster_unknown_dns.py)
UNKNOWN_CLUSTERED_CSV = "unknown_domains_dns_clustered.csv"

# Cluster-level attribution candidates with DNS features
# (from compute_cluster_similarity_dns.py)
ATTR_CSV = "cluster_attribution_candidates_dns.csv"

# ========================================================

EXPECTED_UNKNOWN_COLS = ["domain", "cluster_id"]
EXPECTED_ATTR_COLS = [
    "unknown_cluster_id",
    "known_cluster_id",
    "actor_label",
    "base_similarity",
    "evidence_features",
    "confidence_0_1",
    "confidence_percent",
]


def normalize_domain(d: str) -> str:
    """
    Normalize domain:
      - strip whitespace
      - replace IOC notation 'microsfot[.]org' -> 'microsfot.org'
    """
    d = d.strip()
    d = d.replace("[.]", ".").replace("(.)", ".")
    return d.lower()


def load_data():
    print("[*] Loading data...")

    # Load unknown clustered
    df_unknown = pd.read_csv(UNKNOWN_CLUSTERED_CSV)
    missing_unknown = [c for c in EXPECTED_UNKNOWN_COLS if c not in df_unknown.columns]
    if missing_unknown:
        raise ValueError(
            f"{UNKNOWN_CLUSTERED_CSV} is missing expected columns {missing_unknown}. "
            f"Columns present: {list(df_unknown.columns)}"
        )

    # Load attribution candidates
    df_attr = pd.read_csv(ATTR_CSV)
    missing_attr = [c for c in EXPECTED_ATTR_COLS if c not in df_attr.columns]
    if missing_attr:
        raise ValueError(
            f"{ATTR_CSV} is missing expected columns {missing_attr}. "
            f"Columns present: {list(df_attr.columns)}"
        )

    return df_unknown, df_attr


def attribute_single_domain(domain: str, df_unknown: pd.DataFrame, df_attr: pd.DataFrame):
    dom_norm = normalize_domain(domain)

    # Find domain in unknown clustered set
    mask = df_unknown["domain"].astype(str).str.lower() == dom_norm
    rows = df_unknown[mask]

    print("\n==============================")
    print(f"Domain: {domain} (normalized: {dom_norm})")

    if rows.empty:
        print("  [!] Domain not found in unknown_domains_dns_clustered.csv")
        print("      → You likely need to enrich + re-run clustering including this domain.")
        return

    cluster_id = rows["cluster_id"].iloc[0]
    print(f"  Unknown-domain cluster ID: {cluster_id}")

    # Find attribution candidates for this unknown cluster
    cand = df_attr[df_attr["unknown_cluster_id"] == cluster_id].copy()
    if cand.empty:
        print("  [!] No attribution candidates found for this cluster.")
        return

    cand.sort_values("confidence_0_1", ascending=False, inplace=True)
    top = cand.iloc[0]

    print(f"  Top actor: {top['actor_label']}")
    print(f"  Confidence: {top['confidence_percent']}%")
    print(f"  Base similarity: {top['base_similarity']}")
    print(f"  Evidence features matched: {int(top['evidence_features'])}")

    # Other candidates (if any)
    if len(cand) > 1:
        print("  Other candidates:")
        for _, row in cand.iloc[1:].iterrows():
            print(
                f"    - {row['actor_label']} "
                f"({row['confidence_percent']}%, "
                f"base_sim={row['base_similarity']}, "
                f"features={int(row['evidence_features'])})"
            )
    else:
        print("  (No other candidate actors for this cluster.)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python attribute_domain.py <domain1> [<domain2> ...]")
        sys.exit(1)

    df_unknown, df_attr = load_data()

    # Loop through all domains given on the command line
    for dom in sys.argv[1:]:
        attribute_single_domain(dom, df_unknown, df_attr)


if __name__ == "__main__":
    main()
