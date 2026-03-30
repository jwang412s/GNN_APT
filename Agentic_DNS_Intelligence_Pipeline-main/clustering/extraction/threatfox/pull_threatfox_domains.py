import pathlib
import json
import csv
import requests
import os
from dotenv import load_dotenv


API_URL = "https://threatfox-api.abuse.ch/api/v1/"
AUTH_KEY = "c677c5509e7cf162cb4207d914d1de16a6d48d8feb1a3ff9"


BASE = pathlib.Path(r"C:\ti-threatfox")
OUTDIR = BASE / "actor_domains"
OUTDIR.mkdir(parents=True, exist_ok=True)

RAW_JSON = OUTDIR / "threatfox_raw_iocs.json"
GROUPED_JSON = OUTDIR / "threatfox_actor_domains.json"
FLAT_CSV = OUTDIR / "threatfox_actor_domains_flat.csv"
DOMAINS_TXT = OUTDIR / "threatfox_domains_for_enrichment.txt"

URL = "https://threatfox-api.abuse.ch/api/v1/"

def fetch_iocs(days: int = 7):
    """
    Pull IOCs from ThreatFox for the last N days.
    ThreatFox API constraints:
      - query must be 'get_iocs'
      - days must be between 1 and 7
    """
    if days < 1 or days > 7:
        raise ValueError("ThreatFox get_iocs: 'days' must be between 1 and 7.")

    print(f"[ThreatFox] Fetching IOCs for last {days} days...")

    headers = {
        "Auth-Key": AUTH_KEY
    }

    payload = {
        "query": "get_iocs",
        "days": days
    }

    # Send JSON body with the required Auth-Key header
    r = requests.post(URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()

    status = data.get("query_status")
    if status != "ok":
        raise RuntimeError(f"Unexpected status from ThreatFox: {status}")

    return data.get("data", [])

def build_actor_domain_mapping(iocs):
    """
    Group domain/hostname IOCs by 'malware_printable' (family / actor label).
    """
    actors = {}   # label -> set(domains)
    flat_rows = []  # for CSV / JSONL style use later

    for item in iocs:
        ioc_type = item.get("ioc_type")
        if ioc_type not in ("domain", "hostname"):
            continue

        domain = (item.get("ioc") or "").strip().lower()
        if not domain:
            continue

        # ThreatFox is malware-centric, but malware family often implies actor/campaign
        label = (
            item.get("malware_printable")
            or item.get("malware_alias")
            or item.get("malware")
            or "Unknown"
        )

        if label not in actors:
            actors[label] = set()
        if domain not in actors[label]:
            actors[label].add(domain)
            flat_rows.append({
                "label": label,
                "domain": domain
            })

    return actors, flat_rows

def main():
    iocs = fetch_iocs(days=7)

    # Save raw for debugging
    with RAW_JSON.open("w", encoding="utf-8") as f:
        json.dump(iocs, f, indent=2)
    print(f"[ThreatFox] Raw IOCs saved to {RAW_JSON}")

    actors, flat_rows = build_actor_domain_mapping(iocs)

    # Grouped JSON: label -> domains[]
    grouped = {
        "source": "ThreatFox",
        "description": "Label (malware / actor / family) to domains mapping derived from ThreatFox get_iocs",
        "labels_count": len(actors),
        "labels": {
            label: sorted(list(domains))
            for label, domains in actors.items()
        }
    }

    with GROUPED_JSON.open("w", encoding="utf-8") as f:
        json.dump(grouped, f, indent=2)
    print(f"[ThreatFox] Grouped mapping saved to {GROUPED_JSON}")

    # Flat CSV: label,domain (similar to your OTX flat file)
    with FLAT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "domain"])
        w.writeheader()
        w.writerows(flat_rows)
    print(f"[ThreatFox] Flat CSV saved to {FLAT_CSV}")

    # Unique domain list for enrichment
    unique_domains = sorted({row["domain"] for row in flat_rows})
    with DOMAINS_TXT.open("w", encoding="utf-8") as f:
        for d in unique_domains:
            f.write(d + "\n")
    print(f"[ThreatFox] Domain list saved to {DOMAINS_TXT}")

    print(f"\nSummary:")
    print(f"  Labels with at least one domain: {len(actors)}")
    print(f"  Total (label, domain) pairs: {len(flat_rows)}")
    print(f"  Unique domains: {len(unique_domains)}")

if __name__ == "__main__":
    main()
