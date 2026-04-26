"""
Export the Neo4j TRAIL knowledge graph to PyTorch Geometric HeteroData.

Node types: Domain, IP, URL, Event, ASN
Edge types: InReport, ResolvesTo, InGroup, HostedOn

ASN nodes carry a fixed zero-vector feature at the GNN encoding dim.
Paper §IV-C treats ASNs as structural-only nodes whose value is the
4-hop path Event → IP → ASN → IP → Event they enable for message
passing / label propagation.
"""

import numpy as np
import torch
from datetime import datetime
from torch_geometric.data import HeteroData

from . import config
from .neo4j_client import Neo4jClient
from .vocabularies import VocabularySet
from .feature_extraction import domain_features, ip_features, url_features


def export_graph(client: Neo4jClient, vocabs: VocabularySet) -> HeteroData:
    """
    Pull the full graph from Neo4j and convert to PyG HeteroData.

    Returns a HeteroData object with:
      - Node features for Domain, IP, URL (raw high-dim vectors)
      - Event nodes with APT labels (no features yet — set after AE encoding)
      - All edge types as edge_index tensors
    """
    data = HeteroData()

    # --- Fetch nodes ---
    domains = client.run_query(
        "MATCH (d:Domain) RETURN d.value AS id, d AS props ORDER BY d.value"
    )
    ips = client.run_query(
        "MATCH (ip:IP) RETURN ip.value AS id, ip AS props ORDER BY ip.value"
    )
    urls = client.run_query(
        "MATCH (u:URL) RETURN u.value AS id, u AS props ORDER BY u.value"
    )
    events = client.run_query(
        "MATCH (e:Event) RETURN e.id AS id, e.apt AS apt, "
        "e.label_confidence AS label_confidence, "
        "e.belief_named_actor AS belief_named_actor, "
        "e.belief_nation_state AS belief_nation_state, "
        "e.uncertainty AS uncertainty, "
        "e.tag_exclusivity AS tag_exclusivity, "
        "e.evidence_weight AS evidence_weight, "
        "e.nation_coherence AS nation_coherence, "
        "e.activity_cluster AS activity_cluster "
        "ORDER BY e.id"
    )
    asns = client.run_query(
        "MATCH (a:ASN) RETURN a.number AS id ORDER BY a.number"
    )

    # Build ID → index mappings
    domain_id2idx = {d["id"]: i for i, d in enumerate(domains)}
    ip_id2idx = {ip["id"]: i for i, ip in enumerate(ips)}
    url_id2idx = {u["id"]: i for i, u in enumerate(urls)}
    event_id2idx = {e["id"]: i for i, e in enumerate(events)}
    asn_id2idx = {a["id"]: i for i, a in enumerate(asns)}

    # --- Fetch temporal data from edges and attach to node props ---
    now = datetime.utcnow()

    # Domain temporal: lifespan + recency from ResolvesTo first_seen/last_seen
    domain_temporal = client.run_query(
        "MATCH (d:Domain)-[r:ResolvesTo]->() "
        "WITH d.value AS domain, "
        "  min(r.first_seen) AS first_seen, max(r.last_seen) AS last_seen "
        "RETURN domain, first_seen, last_seen"
    )
    domain_time_map = {}
    for rec in domain_temporal:
        fs, ls = rec.get("first_seen"), rec.get("last_seen")
        lifespan_days, recency_days = 0.0, 0.0
        if fs and ls:
            try:
                fs_dt = datetime.fromisoformat(str(fs).replace("Z", "+00:00").replace("+00:00", ""))
                ls_dt = datetime.fromisoformat(str(ls).replace("Z", "+00:00").replace("+00:00", ""))
                lifespan_days = max(0, (ls_dt - fs_dt).total_seconds() / 86400)
                recency_days = max(0, (now - ls_dt).total_seconds() / 86400)
            except (ValueError, TypeError):
                pass
        domain_time_map[rec["domain"]] = {
            "lifespan_days": lifespan_days,
            "recency_days": recency_days,
        }

    # IP temporal: lifespan + recency from ResolvesTo edges pointing to this IP
    ip_temporal = client.run_query(
        "MATCH ()-[r:ResolvesTo]->(ip:IP) "
        "WITH ip.value AS ip, "
        "  min(r.first_seen) AS first_seen, max(r.last_seen) AS last_seen "
        "RETURN ip, first_seen, last_seen"
    )
    ip_time_map = {}
    for rec in ip_temporal:
        fs, ls = rec.get("first_seen"), rec.get("last_seen")
        lifespan_days, recency_days = 0.0, 0.0
        if fs and ls:
            try:
                fs_dt = datetime.fromisoformat(str(fs).replace("Z", "+00:00").replace("+00:00", ""))
                ls_dt = datetime.fromisoformat(str(ls).replace("Z", "+00:00").replace("+00:00", ""))
                lifespan_days = max(0, (ls_dt - fs_dt).total_seconds() / 86400)
                recency_days = max(0, (now - ls_dt).total_seconds() / 86400)
            except (ValueError, TypeError):
                pass
        ip_time_map[rec["ip"]] = {
            "lifespan_days": lifespan_days,
            "recency_days": recency_days,
        }

    # URL temporal: recency from InReport indicator_created
    url_temporal = client.run_query(
        "MATCH (e:Event)-[r:InReport]->(u:URL) "
        "RETURN u.value AS url, min(r.indicator_created) AS first_seen, "
        "max(r.indicator_created) AS last_seen"
    )
    url_time_map = {}
    for rec in url_temporal:
        fs, ls = rec.get("first_seen"), rec.get("last_seen")
        lifespan_days, recency_days = 0.0, 0.0
        if fs and ls:
            try:
                fs_dt = datetime.fromisoformat(str(fs).replace("Z", "+00:00").replace("+00:00", ""))
                ls_dt = datetime.fromisoformat(str(ls).replace("Z", "+00:00").replace("+00:00", ""))
                lifespan_days = max(0, (ls_dt - fs_dt).total_seconds() / 86400)
                recency_days = max(0, (now - ls_dt).total_seconds() / 86400)
            except (ValueError, TypeError):
                pass
        url_time_map[rec["url"]] = {
            "lifespan_days": lifespan_days,
            "recency_days": recency_days,
        }

    # Inject temporal data into node props
    for d in domains:
        t = domain_time_map.get(d["id"], {})
        d["props"]["lifespan_days"] = t.get("lifespan_days", 0.0)
        d["props"]["recency_days"] = t.get("recency_days", 0.0)

    for ip in ips:
        t = ip_time_map.get(ip["id"], {})
        ip["props"]["lifespan_days"] = t.get("lifespan_days", 0.0)
        ip["props"]["recency_days"] = t.get("recency_days", 0.0)

    for u in urls:
        t = url_time_map.get(u["id"], {})
        u["props"]["lifespan_days"] = t.get("lifespan_days", 0.0)
        u["props"]["recency_days"] = t.get("recency_days", 0.0)

    # --- Build feature matrices ---
    if domains:
        domain_feats = np.stack([
            domain_features(d["props"], vocabs) for d in domains
        ])
        data["domain"].x = torch.from_numpy(domain_feats)
    else:
        data["domain"].x = torch.zeros((0, config.DOMAIN_FEATURE_DIM))

    if ips:
        ip_feats = np.stack([
            ip_features(ip["props"], vocabs) for ip in ips
        ])
        data["ip"].x = torch.from_numpy(ip_feats)
    else:
        data["ip"].x = torch.zeros((0, config.IP_FEATURE_DIM))

    if urls:
        url_feats = np.stack([
            url_features(u["props"], vocabs) for u in urls
        ])
        data["url"].x = torch.from_numpy(url_feats)
    else:
        data["url"].x = torch.zeros((0, config.URL_FEATURE_DIM))

    # ASN nodes are structural-only. Features are a zero vector at the
    # AE encoding dim so heterogeneous message passing sees the same
    # shape as post-AE Domain/IP/URL features. The GNN still learns
    # weights on the in_group / rev_in_group relations, which is the
    # whole point of including ASN nodes.
    num_asns = len(asns)
    if num_asns > 0:
        data["asn"].x = torch.zeros((num_asns, config.ASN_FEATURE_DIM),
                                    dtype=torch.float32)
    else:
        data["asn"].x = torch.zeros((0, config.ASN_FEATURE_DIM),
                                    dtype=torch.float32)

    # Event nodes: placeholder features (will be set after AE encoding)
    # Store labels for training
    num_events = len(events)
    data["event"].num_nodes = num_events

    labels = torch.full((num_events,), -1, dtype=torch.long)
    for i, e in enumerate(events):
        apt = e.get("apt")
        if apt and apt in config.APT_TO_IDX:
            labels[i] = config.APT_TO_IDX[apt]
    data["event"].y = labels

    # Mask: which events have known labels
    data["event"].train_mask = labels >= 0

    # DST label_confidence from v5 Independent DST.
    # Measures how trustworthy this event's APT label is (per-pulse, not accumulated).
    # Used as per-sample weight during GNN training so high-confidence events
    # contribute more to the loss than noisy ones.
    label_confidence = torch.ones(num_events, dtype=torch.float32)
    for i, e in enumerate(events):
        conf = e.get("label_confidence") or e.get("belief_named_actor")
        if conf is not None:
            label_confidence[i] = max(float(conf), 0.1)  # floor at 0.1 to avoid zero-weight
    data["event"].label_confidence = label_confidence

    # --- Fetch and build edges ---

    # Event -[InReport]-> Domain
    e_d = client.run_query(
        "MATCH (e:Event)-[:InReport]->(d:Domain) RETURN e.id AS eid, d.value AS did"
    )
    _add_edges(data, e_d, "eid", "did", event_id2idx, domain_id2idx,
               ("event", "in_report", "domain"))

    # Event -[InReport]-> IP
    e_ip = client.run_query(
        "MATCH (e:Event)-[:InReport]->(ip:IP) RETURN e.id AS eid, ip.value AS ipid"
    )
    _add_edges(data, e_ip, "eid", "ipid", event_id2idx, ip_id2idx,
               ("event", "in_report", "ip"))

    # Event -[InReport]-> URL
    e_u = client.run_query(
        "MATCH (e:Event)-[:InReport]->(u:URL) RETURN e.id AS eid, u.value AS uid"
    )
    _add_edges(data, e_u, "eid", "uid", event_id2idx, url_id2idx,
               ("event", "in_report", "url"))

    # Domain -[ResolvesTo]-> IP
    d_ip = client.run_query(
        "MATCH (d:Domain)-[:ResolvesTo]->(ip:IP) RETURN d.value AS did, ip.value AS ipid"
    )
    _add_edges(data, d_ip, "did", "ipid", domain_id2idx, ip_id2idx,
               ("domain", "resolves_to", "ip"))

    # URL -[HostedOn]-> Domain
    u_d = client.run_query(
        "MATCH (u:URL)-[:HostedOn]->(d:Domain) RETURN u.value AS uid, d.value AS did"
    )
    _add_edges(data, u_d, "uid", "did", url_id2idx, domain_id2idx,
               ("url", "hosted_on", "domain"))

    # URL -[ResolvesTo]-> IP
    u_ip = client.run_query(
        "MATCH (u:URL)-[:ResolvesTo]->(ip:IP) RETURN u.value AS uid, ip.value AS ipid"
    )
    _add_edges(data, u_ip, "uid", "ipid", url_id2idx, ip_id2idx,
               ("url", "resolves_to_ip", "ip"))

    # IP -[InGroup]-> ASN  (paper §IV-C — enables 4-hop Event→IP→ASN→IP→Event path)
    if num_asns > 0:
        ip_asn = client.run_query(
            "MATCH (ip:IP)-[:InGroup]->(a:ASN) "
            "RETURN ip.value AS ipid, a.number AS aid"
        )
        _add_edges(data, ip_asn, "ipid", "aid", ip_id2idx, asn_id2idx,
                   ("ip", "in_group", "asn"))

    # Add reverse edges for message passing (GNN needs bidirectional)
    _add_reverse_edges(data)

    # Store mappings for later use
    data.domain_id2idx = domain_id2idx
    data.ip_id2idx = ip_id2idx
    data.url_id2idx = url_id2idx
    data.event_id2idx = event_id2idx
    data.asn_id2idx = asn_id2idx

    return data


def _add_edges(
    data: HeteroData,
    records: list[dict],
    src_key: str,
    dst_key: str,
    src_map: dict[str, int],
    dst_map: dict[str, int],
    edge_type: tuple[str, str, str],
):
    """Add edge_index for a given edge type from query results."""
    src_ids, dst_ids = [], []
    for r in records:
        s = src_map.get(r[src_key])
        d = dst_map.get(r[dst_key])
        if s is not None and d is not None:
            src_ids.append(s)
            dst_ids.append(d)

    if src_ids:
        edge_index = torch.tensor([src_ids, dst_ids], dtype=torch.long)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)

    data[edge_type].edge_index = edge_index


def _add_reverse_edges(data: HeteroData):
    """Add reverse edge types for bidirectional message passing."""
    edge_types = list(data.edge_types)
    for src, rel, dst in edge_types:
        rev_type = (dst, f"rev_{rel}", src)
        if rev_type not in data.edge_types:
            ei = data[(src, rel, dst)].edge_index
            data[rev_type].edge_index = ei.flip(0)
