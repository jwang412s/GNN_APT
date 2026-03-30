"""
Load the TRAIL Knowledge Graph (TKG) published dataset into Neo4j.

Reads:
  - TKG_data/otx_dataset/full_graph_csr.pt  (graph structure + labels)
  - TKG_data/otx_dataset/domains.csv        (domain IOC features)
  - TKG_data/otx_dataset/ips.csv            (IP IOC features)
  - TKG_data/otx_dataset/urls.csv           (URL IOC features)

Writes into Neo4j (PaperTrail instance):
  - Event nodes with APT label + nation_state + cluster
  - Domain nodes with features
  - IP nodes with features
  - URL nodes with features
  - ASN nodes
  - All edges: InReport, ResolvesTo, HostedOn, InGroup

Resume-safe: uses MERGE for nodes and checks existing edge counts
to skip completed edge types on restart.

Usage:
  python load_tkg_to_neo4j.py
"""

import sys
import os
import time
from collections import defaultdict

import math

import torch
import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# --- Config ---
NEO4J_URL = "http://localhost:7474/db/neo4j/tx/commit"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "trailpassword"
BATCH_SIZE = 500

# Nation-state mapping (same as our project)
APT_TO_NATION = {
    "APT28": "Russia", "APT29": "Russia", "TURLA": "Russia",
    "APT37": "North Korea", "APT38": "North Korea", "KIMSUKY": "North Korea",
    "APT27": "China", "MUSTANG PANDA": "China",
    "APT41": "China", "MUDDYWATER": "Iran", "APT34": "Iran", "APT35": "Iran",
    "FIN11": "Cybercrime", "FIN7": "Cybercrime", "COBALT GROUP": "Cybercrime",
    "MAGECART": "Cybercrime", "GOLD WATERFALL": "Cybercrime",
    "TA511": "Cybercrime", "TA551": "Cybercrime",
    "MOLERATS": "Palestine", "BLACKENERGY": "Russia", "TEAMTNT": "Cybercrime",
}

NATION_TO_CLUSTER = {
    "Russia": "State-Sponsored", "North Korea": "State-Sponsored",
    "China": "State-Sponsored", "Iran": "State-Sponsored",
    "Palestine": "State-Sponsored", "Vietnam": "State-Sponsored",
    "Cybercrime": "Cybercrime",
}


def safe_float(v, default=0.0):
    """Convert to float, replacing NaN/inf with default."""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def safe_int(v, default=0):
    """Convert to int, handling NaN."""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


def neo4j_query(statements):
    """Execute a list of Cypher statements against Neo4j."""
    payload = {"statements": statements}
    resp = requests.post(
        NEO4J_URL,
        json=payload,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
        headers={"Content-Type": "application/json"},
    )
    result = resp.json()
    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Neo4j error: {err['message'][:200]}")
    return result


def neo4j_batch(cypher, param_list, label="", start_from=0):
    """Execute a parameterized Cypher statement in batches, with resume support."""
    total = len(param_list)
    for i in range(start_from, total, BATCH_SIZE):
        batch = param_list[i : i + BATCH_SIZE]
        statements = [{"statement": cypher, "parameters": p} for p in batch]
        neo4j_query(statements)
        done = min(i + BATCH_SIZE, total)
        print(f"\r  {label}: {done}/{total}", end="", flush=True)
    print()


def get_existing_counts():
    """Check what's already in Neo4j for resume logic."""
    node_result = neo4j_query([
        {"statement": "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"}
    ])
    edge_result = neo4j_query([
        {"statement": "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"}
    ])

    node_counts = {}
    if node_result.get("results"):
        for row in node_result["results"][0]["data"]:
            node_counts[row["row"][0]] = row["row"][1]

    edge_counts = {}
    if edge_result.get("results"):
        for row in edge_result["results"][0]["data"]:
            edge_counts[row["row"][0]] = row["row"][1]

    return node_counts, edge_counts


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    pt_path = os.path.join(base, "TKG_data", "otx_dataset", "full_graph_csr.pt")

    print("Loading graph structure...")
    data = torch.load(pt_path, map_location="cpu", weights_only=False)

    print(f"  Nodes: {data.x.shape[0]:,}")
    print(f"  Events: {data.event_ids.shape[0]:,}")
    print(f"  Edges: {data.edge_csr.idx.shape[0]:,}")
    print(f"  APT groups: {len(data.label_map)}")
    print()

    # --- Check existing state for resume ---
    print("Checking existing Neo4j state...")
    node_counts, edge_counts = get_existing_counts()
    if node_counts:
        print(f"  Existing nodes: {node_counts}")
    if edge_counts:
        print(f"  Existing edges: {edge_counts}")
    print()

    # --- Load CSVs ---
    print("Loading CSV features...")
    csv_dir = os.path.join(base, "TKG_data", "otx_dataset")
    domains_df = pd.read_csv(os.path.join(csv_dir, "domains.csv"), sep="\t")
    ips_df = pd.read_csv(os.path.join(csv_dir, "ips.csv"), sep="\t")
    urls_df = pd.read_csv(os.path.join(csv_dir, "urls.csv"), sep="\t")
    print(f"  Domains: {len(domains_df):,}, IPs: {len(ips_df):,}, URLs: {len(urls_df):,}")
    print()

    # --- Build node_id -> IOC value lookup ---
    print("Building node lookups...")
    ntypes = data.ntypes
    node_type = data.x
    feat_map = data.feat_map

    domain_nodes = (node_type == ntypes["domains"]).nonzero(as_tuple=True)[0].tolist()
    ip_nodes = (node_type == ntypes["ips"]).nonzero(as_tuple=True)[0].tolist()
    url_nodes = (node_type == ntypes["urls"]).nonzero(as_tuple=True)[0].tolist()
    asn_nodes = (node_type == ntypes["ASN"]).nonzero(as_tuple=True)[0].tolist()
    event_node_ids = data.event_ids.tolist()

    node_to_ioc = {}

    for nid in domain_nodes:
        row = feat_map[nid].item()
        if row >= 0 and row < len(domains_df):
            node_to_ioc[nid] = ("domain", domains_df.iloc[row]["ioc"])

    for nid in ip_nodes:
        row = feat_map[nid].item()
        if row >= 0 and row < len(ips_df):
            node_to_ioc[nid] = ("ip", ips_df.iloc[row]["ioc"])

    for nid in url_nodes:
        row = feat_map[nid].item()
        if row >= 0 and row < len(urls_df):
            node_to_ioc[nid] = ("url", urls_df.iloc[row]["ioc"])

    for nid in asn_nodes:
        node_to_ioc[nid] = ("asn", str(nid))

    for i, eid in enumerate(event_node_ids):
        label = data.label_map[data.y[i].item()]
        node_to_ioc[eid] = ("event", label)

    print(f"  Mapped {len(node_to_ioc):,} nodes to IOC values")
    print()

    # --- Create Neo4j indexes ---
    print("Creating indexes...")
    neo4j_query([
        {"statement": "CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.node_id)"},
        {"statement": "CREATE INDEX IF NOT EXISTS FOR (d:Domain) ON (d.value)"},
        {"statement": "CREATE INDEX IF NOT EXISTS FOR (ip:IP) ON (ip.value)"},
        {"statement": "CREATE INDEX IF NOT EXISTS FOR (u:URL) ON (u.value)"},
        {"statement": "CREATE INDEX IF NOT EXISTS FOR (a:ASN) ON (a.node_id)"},
    ])
    time.sleep(2)
    print()

    # --- Write Event nodes (MERGE = idempotent) ---
    expected_events = len(event_node_ids)
    if node_counts.get("Event", 0) >= expected_events:
        print(f"Skipping Event nodes (already {node_counts['Event']:,})")
    else:
        print("Writing Event nodes...")
        event_params = []
        for i, eid in enumerate(event_node_ids):
            apt = data.label_map[data.y[i].item()]
            nation = APT_TO_NATION.get(apt, "Unknown")
            cluster = NATION_TO_CLUSTER.get(nation, "Unknown")
            event_params.append({
                "node_id": eid, "apt": apt,
                "nation_state": nation, "cluster": cluster,
            })
        neo4j_batch(
            "MERGE (e:Event {node_id: $node_id}) SET e.apt = $apt, e.nation_state = $nation_state, e.cluster = $cluster",
            event_params, label="Events",
        )

    # --- Write Domain nodes ---
    if node_counts.get("Domain", 0) >= len(domain_nodes):
        print(f"Skipping Domain nodes (already {node_counts['Domain']:,})")
    else:
        print("Writing Domain nodes...")
        domain_params = []
        for nid in domain_nodes:
            row = feat_map[nid].item()
            if row < 0 or row >= len(domains_df):
                continue
            r = domains_df.iloc[row]
            domain_params.append({
                "node_id": nid, "value": str(r["ioc"]),
                "entropy": safe_float(r.get("domain_entropy", 0)),
                "length": safe_int(r.get("domain_length", 0)),
                "num_digits": safe_int(r.get("num_digits", 0)),
                "subdomains": safe_int(r.get("subdomains", 0)),
                "has_nxdomain": bool(safe_int(r.get("has_nxdomain", 0))),
                "first_seen": safe_float(r.get("first_seen", 0)),
                "last_seen": safe_float(r.get("last_seen", 0)),
            })
        neo4j_batch(
            """MERGE (d:Domain {node_id: $node_id})
            SET d.value = $value, d.entropy = $entropy, d.length = $length,
                d.num_digits = $num_digits, d.subdomains = $subdomains,
                d.has_nxdomain = $has_nxdomain, d.first_seen = $first_seen,
                d.last_seen = $last_seen""",
            domain_params, label="Domains",
        )

    # --- Write IP nodes ---
    if node_counts.get("IP", 0) >= len(ip_nodes):
        print(f"Skipping IP nodes (already {node_counts['IP']:,})")
    else:
        print("Writing IP nodes...")
        ip_params = []
        for nid in ip_nodes:
            row = feat_map[nid].item()
            if row < 0 or row >= len(ips_df):
                continue
            r = ips_df.iloc[row]
            ip_params.append({"node_id": nid, "value": str(r["ioc"])})
        neo4j_batch(
            "MERGE (ip:IP {node_id: $node_id}) SET ip.value = $value",
            ip_params, label="IPs",
        )

    # --- Write URL nodes ---
    if node_counts.get("URL", 0) >= len(url_nodes):
        print(f"Skipping URL nodes (already {node_counts['URL']:,})")
    else:
        print("Writing URL nodes...")
        url_params = []
        for nid in url_nodes:
            row = feat_map[nid].item()
            if row < 0 or row >= len(urls_df):
                continue
            r = urls_df.iloc[row]
            url_params.append({
                "node_id": nid, "value": str(r["ioc"]),
                "entropy": safe_float(r.get("url_entropy", 0)),
                "length": safe_int(r.get("url_length", 0)),
                "num_digits": safe_int(r.get("num_digits", 0)),
                "path_length": safe_int(r.get("url_path_length", 0)),
            })
        neo4j_batch(
            """MERGE (u:URL {node_id: $node_id})
            SET u.value = $value, u.entropy = $entropy, u.length = $length,
                u.num_digits = $num_digits, u.path_length = $path_length""",
            url_params, label="URLs",
        )

    # --- Write ASN nodes ---
    if node_counts.get("ASN", 0) >= len(asn_nodes):
        print(f"Skipping ASN nodes (already {node_counts['ASN']:,})")
    else:
        print("Writing ASN nodes...")
        asn_params = [{"node_id": nid} for nid in asn_nodes]
        neo4j_batch(
            "MERGE (a:ASN {node_id: $node_id})",
            asn_params, label="ASNs",
        )

    # --- Write edges ---
    print("\nExtracting edges...")
    csr = data.edge_csr
    edge_batches = defaultdict(list)
    total_nodes = data.x.shape[0]

    for src_node in range(total_nodes):
        start = csr.ptr[src_node]
        end = csr.ptr[src_node + 1]
        if start == end:
            continue

        src_info = node_to_ioc.get(src_node)
        if not src_info:
            continue
        src_type = src_info[0]

        for dst_node in csr.idx[start:end].tolist():
            dst_info = node_to_ioc.get(dst_node)
            if not dst_info:
                continue
            dst_type = dst_info[0]
            edge_batches[(src_type, dst_type)].append((src_node, dst_node))

        if src_node % 100000 == 0:
            print(f"\r  Scanning edges: {src_node:,}/{total_nodes:,}", end="", flush=True)

    print(f"\r  Scanning edges: {total_nodes:,}/{total_nodes:,}")
    print()

    edge_type_map = {
        ("event", "domain"): ("InReport", "Event", "node_id", "Domain", "node_id"),
        ("event", "url"): ("InReport", "Event", "node_id", "URL", "node_id"),
        ("event", "ip"): ("InReport", "Event", "node_id", "IP", "node_id"),
        ("domain", "ip"): ("ResolvesTo", "Domain", "node_id", "IP", "node_id"),
        ("ip", "domain"): ("ResolvesTo", "IP", "node_id", "Domain", "node_id"),
        ("url", "domain"): ("HostedOn", "URL", "node_id", "Domain", "node_id"),
        ("url", "ip"): ("ResolvesTo", "URL", "node_id", "IP", "node_id"),
        ("ip", "asn"): ("InGroup", "IP", "node_id", "ASN", "node_id"),
        # Reverse edges (graph is stored bidirectionally)
        ("domain", "event"): ("InReport_REV", "Domain", "node_id", "Event", "node_id"),
        ("url", "event"): ("InReport_REV", "URL", "node_id", "Event", "node_id"),
        ("ip", "event"): ("InReport_REV", "IP", "node_id", "Event", "node_id"),
        ("domain", "url"): ("HostedOn_REV", "Domain", "node_id", "URL", "node_id"),
        ("ip", "url"): ("ResolvesTo_REV", "IP", "node_id", "URL", "node_id"),
        ("asn", "ip"): ("InGroup_REV", "ASN", "node_id", "IP", "node_id"),
    }

    # Count expected edges per relationship type (forward only)
    expected_edge_counts = defaultdict(int)
    for (src_t, dst_t), edges in edge_batches.items():
        mapping = edge_type_map.get((src_t, dst_t))
        if not mapping or mapping[0].endswith("_REV"):
            continue
        expected_edge_counts[mapping[0]] += len(edges)

    for (src_t, dst_t), edges in edge_batches.items():
        mapping = edge_type_map.get((src_t, dst_t))
        if not mapping:
            print(f"  Skipping unknown edge type: {src_t} -> {dst_t} ({len(edges)} edges)")
            continue

        rel_type, src_label, src_key, dst_label, dst_key = mapping

        if rel_type.endswith("_REV"):
            print(f"  Skipping reverse edges: {src_t} -> {dst_t} ({len(edges):,})")
            continue

        # Resume logic: skip if this edge type is already complete
        existing = edge_counts.get(rel_type, 0)
        expected = expected_edge_counts[rel_type]
        if existing >= expected:
            print(f"  Skipping {rel_type} (already {existing:,} >= expected {expected:,})")
            continue

        if existing > 0:
            print(f"  Resuming {rel_type}: {src_t} -> {dst_t} ({len(edges):,} edges, {existing:,} already exist)")
            print(f"  WARNING: {existing:,} edges already exist. Using MERGE to avoid duplicates.")

        print(f"  Writing {rel_type}: {src_t} -> {dst_t} ({len(edges):,} edges)")
        params = [{"src": s, "dst": d} for s, d in edges]

        cypher = (
            f"MATCH (a:{src_label} {{{src_key}: $src}}) "
            f"MATCH (b:{dst_label} {{{dst_key}: $dst}}) "
            f"MERGE (a)-[:{rel_type}]->(b)"
        )
        neo4j_batch(cypher, params, label=rel_type)

    print("\nDone! Graph loaded into Neo4j.")

    # Print summary
    result = neo4j_query([
        {"statement": "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"}
    ])
    if result.get("results"):
        print("\n=== Neo4j Summary ===")
        for row in result["results"][0]["data"]:
            print(f"  {row['row'][0]}: {row['row'][1]:,}")

    result2 = neo4j_query([
        {"statement": "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"}
    ])
    if result2.get("results"):
        print()
        for row in result2["results"][0]["data"]:
            print(f"  {row['row'][0]}: {row['row'][1]:,}")


if __name__ == "__main__":
    main()
