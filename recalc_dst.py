#!/usr/bin/env python3
"""
recalc_dst.py — Recalculate Independent DST beliefs on existing Event nodes.

Instead of re-running the full n8n workflow, this script:
1. Queries Neo4j for all Event node pulse IDs
2. Fetches pulse metadata from OTX (tags + indicator counts)
3. Computes independent per-pulse DST mass functions
4. Updates Event nodes with new label_confidence fields

Usage:
    python3 recalc_dst.py

Requires: requests
"""

import os
import math
import time
import requests
import json

# ── Config ──────────────────────────────────────────────────────────
NEO4J_HTTP = os.environ.get("NEO4J_HTTP_URL", "http://localhost:7474")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "trailpassword")
OTX_API_KEY = os.environ.get("OTX_API_KEY", "")

# Try to load OTX key from common locations
if not OTX_API_KEY:
    for path in ["~/.otx_api_key", "~/.config/otx/api_key"]:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            OTX_API_KEY = open(expanded).read().strip()
            break

NATION_MAP = {
    "APT28": "Russia", "APT29": "Russia", "Turla": "Russia",
    "APT37": "North Korea", "APT38": "North Korea", "Kimsuky": "North Korea",
    "APT27": "China", "Mustang Panda": "China", "OceanLotus": "Vietnam",
    "FIN11": "Cybercrime",
}

CLUSTER_MAP = {
    "Russia": "State-Sponsored", "North Korea": "State-Sponsored",
    "China": "State-Sponsored", "Vietnam": "State-Sponsored",
    "Cybercrime": "Cybercrime",
}

MITRE_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"


# ── Neo4j helpers ───────────────────────────────────────────────────
def neo4j_query(statements):
    """Execute Cypher statements via Neo4j HTTP API."""
    resp = requests.post(
        f"{NEO4J_HTTP}/db/neo4j/tx/commit",
        auth=(NEO4J_USER, NEO4J_PASS),
        json={"statements": [{"statement": s} if isinstance(s, str) else s for s in statements]},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(f"Neo4j errors: {data['errors']}")
    return data["results"]


# ── MITRE alias dictionary ─────────────────────────────────────────
def build_alias_dict():
    """Fetch MITRE ATT&CK and build {canonical_name: [lowercase aliases]}."""
    print("Fetching MITRE ATT&CK intrusion sets...")
    resp = requests.get(MITRE_URL, timeout=60)
    resp.raise_for_status()
    mitre = resp.json()

    alias_dict = {}
    for obj in mitre["objects"]:
        if obj.get("type") != "intrusion-set":
            continue
        name = obj["name"]
        aliases = list(set(obj.get("aliases", []) + [name]))
        alias_dict[name] = [a.lower() for a in aliases]

    print(f"  Found {len(alias_dict)} intrusion sets")
    return alias_dict


# ── OTX pulse fetch ────────────────────────────────────────────────
def fetch_pulse(pulse_id, retries=3):
    """Fetch a single pulse's metadata from OTX."""
    headers = {}
    if OTX_API_KEY:
        headers["X-OTX-API-KEY"] = OTX_API_KEY

    for attempt in range(retries):
        try:
            resp = requests.get(
                f"https://otx.alienvault.com/api/v1/pulses/{pulse_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt+1}/{retries}: {e}")
                time.sleep(10 * (attempt + 1))
            else:
                print(f"  FAILED to fetch pulse {pulse_id}: {e}")
                return None
    return None


# ── Independent DST calculation ────────────────────────────────────
def compute_independent_dst(pulse, canonical_target, alias_dict):
    """
    Compute per-pulse independent DST mass function.

    Returns dict with:
        label_confidence, belief_named_actor, belief_nation_state,
        uncertainty, tag_exclusivity, evidence_weight, nation_coherence
    """
    tags = [t.lower() for t in (pulse.get("tags") or [])]
    indicators = pulse.get("indicators") or []
    network_iocs = [
        i for i in indicators
        if i.get("type") in ("domain", "hostname", "IPv4", "URL")
    ]

    target_nation = NATION_MAP.get(canonical_target, "Unknown")

    # If no network IOCs, return zero confidence
    if not network_iocs:
        return {
            "label_confidence": 0.0,
            "belief_named_actor": 0.0,
            "belief_nation_state": 0.0,
            "uncertainty": 1.0,
            "tag_exclusivity": 0.0,
            "evidence_weight": 0.0,
            "nation_coherence": 1.0,
        }

    # ── Signal 1: Tag Exclusivity ──
    # When APT alias tags exist: (target_matches / total_apt_matches)²
    # When no APT alias tags: derive baseline from pulse text.
    #   Rationale: pulse was returned by OTX search for this APT, so the
    #   search query itself is evidence. Baseline = 1/(1+N) where N is the
    #   number of distinct APT groups mentioned in the pulse title/description.
    #   This follows from the principle of insufficient reason — with N
    #   competing hypotheses, each gets equal probability 1/N, and our target
    #   gets 1/(1+N) accounting for the "none of the above" possibility.
    target_alias_count = 0
    total_apt_alias_count = 0
    cross_nation_conflict = False
    other_groups = []

    for canonical, aliases in alias_dict.items():
        matching = [a for a in aliases if a in tags]
        if matching:
            total_apt_alias_count += len(matching)
            if canonical == canonical_target:
                target_alias_count += len(matching)
            else:
                other_groups.append(canonical)
                other_nation = NATION_MAP.get(canonical, "Unknown")
                if other_nation != target_nation:
                    cross_nation_conflict = True

    if total_apt_alias_count > 0:
        # Tags contain APT aliases — use tag-based exclusivity
        tag_exclusivity = (target_alias_count / total_apt_alias_count) ** 2
    else:
        # No APT alias tags — derive baseline from pulse text
        # Count distinct APT groups mentioned in title + description
        pulse_text = (
            (pulse.get("name") or "") + " " + (pulse.get("description") or "")
        ).lower()
        distinct_apts_in_text = 0
        for canonical, aliases in alias_dict.items():
            if any(a in pulse_text for a in aliases):
                distinct_apts_in_text += 1
        # 1/(1+N): principle of insufficient reason
        # 1 APT in text → 0.5, 2 → 0.33, 3 → 0.25
        tag_exclusivity = 1.0 / (1.0 + max(distinct_apts_in_text, 1))

    # ── Signal 2: Nation Coherence ──
    # 1.0 = pulse nation matches APT nation (binary confirmation)
    # 0.5 = no nation info or same-nation overlap (DST maximum ignorance —
    #        equal probability of supporting or contradicting)
    # 0.0 = pulse tags a different nation (contradictory evidence)
    if cross_nation_conflict:
        nation_coherence = 0.0
    elif other_groups:
        nation_coherence = 0.5  # Same-nation overlap — maximum ignorance
    else:
        nation_coherence = 1.0  # Clean match or no competing groups

    # ── Signal 3: Evidence Weight ──
    ioc_count = len(network_iocs)
    evidence_weight = min(1.0, math.log2(1 + ioc_count) / math.log2(51))

    # ── Mass function ──
    m_named = tag_exclusivity * evidence_weight * nation_coherence
    m_nation_only = (1 - tag_exclusivity) * evidence_weight * nation_coherence * 0.5

    # Hierarchical beliefs — tiers are nested, not independent:
    #   Named Actor (APT28) ⊂ Nation-State (Russia) ⊂ Activity Cluster
    #   Knowing APT28 implies knowing Russia, so nation belief subsumes named.
    belief_named = m_named
    belief_nation = m_named + m_nation_only  # always >= belief_named
    m_unknown = 1.0 - belief_named - m_nation_only

    # Clamp to avoid floating point negatives
    m_unknown = max(0.0, m_unknown)

    # Activity cluster: looked up from NATION_MAP, not calculated.
    # If APT has a known nation-state sponsor → "State-Sponsored"
    # If no known state sponsor → "Cybercrime" (default)
    activity_cluster = CLUSTER_MAP.get(target_nation, "Cybercrime")

    return {
        "label_confidence": round(belief_named, 4),
        "belief_named_actor": round(belief_named, 4),
        "belief_nation_state": round(belief_nation, 4),
        "uncertainty": round(m_unknown, 4),
        "tag_exclusivity": round(tag_exclusivity, 4),
        "evidence_weight": round(evidence_weight, 4),
        "nation_coherence": nation_coherence,
        "activity_cluster": activity_cluster,
    }


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Independent DST Recalculation")
    print("=" * 60)

    # Step 1: Get all Event nodes from Neo4j
    print("\n[1/4] Querying Neo4j for Event nodes...")
    results = neo4j_query([
        "MATCH (e:Event) RETURN e.id AS pulse_id, e.apt AS apt, e.name AS name ORDER BY e.apt"
    ])
    events = [row["row"] for row in results[0]["data"]]
    print(f"  Found {len(events)} Event nodes")

    if not events:
        print("No events to process. Exiting.")
        return

    # Show APT distribution
    apt_counts = {}
    for _, apt, _ in events:
        apt_counts[apt] = apt_counts.get(apt, 0) + 1
    for apt, count in sorted(apt_counts.items(), key=lambda x: -x[1]):
        print(f"    {apt}: {count} pulses")

    # Step 2: Build MITRE alias dictionary
    print("\n[2/4] Building MITRE alias dictionary...")
    alias_dict = build_alias_dict()

    # Step 3: Fetch pulse metadata and compute DST
    print(f"\n[3/4] Fetching pulse metadata from OTX and computing DST...")
    updates = []
    for i, (pulse_id, apt, name) in enumerate(events):
        print(f"  [{i+1}/{len(events)}] {apt} — {name[:50]}...", end="")

        pulse = fetch_pulse(pulse_id)
        if not pulse:
            print(" SKIP (fetch failed)")
            continue

        dst = compute_independent_dst(pulse, apt, alias_dict)
        dst["pulse_id"] = pulse_id
        updates.append(dst)

        print(f" → confidence={dst['label_confidence']:.4f} "
              f"(excl={dst['tag_exclusivity']:.2f}, "
              f"weight={dst['evidence_weight']:.2f}, "
              f"nation={dst['nation_coherence']:.1f})")

        # Gentle rate limiting
        if i < len(events) - 1:
            time.sleep(1)

    # Step 4: Update Neo4j
    print(f"\n[4/4] Updating {len(updates)} Event nodes in Neo4j...")
    batch_size = 20
    updated = 0

    for batch_start in range(0, len(updates), batch_size):
        batch = updates[batch_start:batch_start + batch_size]
        statements = []
        for u in batch:
            statements.append({
                "statement": (
                    "MATCH (e:Event {id: $pulse_id}) "
                    "SET e.label_confidence = $label_confidence, "
                    "    e.belief_named_actor = $belief_named_actor, "
                    "    e.belief_nation_state = $belief_nation_state, "
                    "    e.uncertainty = $uncertainty, "
                    "    e.tag_exclusivity = $tag_exclusivity, "
                    "    e.evidence_weight = $evidence_weight, "
                    "    e.nation_coherence = $nation_coherence, "
                    "    e.activity_cluster = $activity_cluster "
                    "RETURN e.id"
                ),
                "parameters": u,
            })
        neo4j_query(statements)
        updated += len(batch)
        print(f"  Updated {updated}/{len(updates)} events")

    # Summary
    print("\n" + "=" * 60)
    print("DONE — Independent DST recalculation complete")
    print("=" * 60)

    # Show results
    results = neo4j_query([
        "MATCH (e:Event) RETURN e.apt AS apt, e.name AS name, "
        "e.label_confidence AS conf, e.tag_exclusivity AS excl, "
        "e.evidence_weight AS weight, e.nation_coherence AS nation "
        "ORDER BY e.apt, conf DESC"
    ])
    print(f"\n{'APT':<20} {'Confidence':>10} {'Exclusivity':>12} {'Weight':>8} {'Nation':>8}  Pulse Name")
    print("-" * 100)
    for row in results[0]["data"]:
        apt, name, conf, excl, weight, nation = row["row"]
        name_short = (name or "")[:35]
        print(f"{apt:<20} {conf or 0:>10.4f} {excl or 0:>12.4f} {weight or 0:>8.4f} {nation or 0:>8.1f}  {name_short}")


if __name__ == "__main__":
    main()
