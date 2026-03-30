import argparse
import socket
from typing import List, Dict, Any, Optional
import dns.resolver
from ipwhois import IPWhois
import whois as python_whois
import pandas as pd
from datetime import datetime


def resolve_domain(domain: str) -> List[str]:
    """
    Resolve a domain to its A records (IPv4).
    Returns a list of IP strings. Empty list on failure.
    """
    ips = set()
    try:
        answers = dns.resolver.resolve(domain, "A")
        for rdata in answers:
            ips.add(rdata.address)
    except Exception:
        # Fallback to socket.gethostbyname_ex
        try:
            _, _, addr_list = socket.gethostbyname_ex(domain)
            ips.update(addr_list)
        except Exception:
            pass
    return sorted(ips)


def get_asn_info(ip: str) -> Dict[str, Any]:
    """
    Use ipwhois to fetch ASN info for an IP.
    Returns a dict with keys asn, asn_description, country, etc.
    On failure, returns empty values.
    """
    try:
        obj = IPWhois(ip)
        res = obj.lookup_rdap(asn_methods=["whois", "http"])
        asn = res.get("asn", "")
        asn_desc = res.get("asn_description", "")
        country = res.get("asn_country_code", "")
        return {
            "asn": asn or "",
            "asn_description": asn_desc or "",
            "asn_country": country or "",
        }
    except Exception:
        return {
            "asn": "",
            "asn_description": "",
            "asn_country": "",
        }


def normalize_whois_date(value) -> Optional[str]:
    """
    WHOIS dates can be datetime, list, string, or None.
    Normalize to ISO string YYYY-MM-DD or return None.
    """
    if isinstance(value, list) and value:
        value = value[0]

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, str):
        try:
            # Try to parse with common formats
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(value[:19], fmt)
                    return dt.date().isoformat()
                except ValueError:
                    continue
        except Exception:
            return None
    return None


def get_whois_info(domain: str) -> Dict[str, Any]:
    """
    Fetch WHOIS info for domain (registrar, creation_date, expiration_date).
    Uses python-whois package.
    """
    try:
        w = python_whois.whois(domain)
        registrar = w.get("registrar") or ""
        creation_date = normalize_whois_date(w.get("creation_date"))
        expiration_date = normalize_whois_date(w.get("expiration_date"))
        return {
            "registrar": registrar,
            "creation_date": creation_date or "",
            "expiration_date": expiration_date or "",
        }
    except Exception:
        return {
            "registrar": "",
            "creation_date": "",
            "expiration_date": "",
        }


def parse_domain_parts(domain: str) -> Dict[str, Any]:
    """
    Very simple domain parsing: split off TLD by last dot.
    For more robust parsing you can use tldextract, but this keeps dependencies minimal.
    """
    parts = domain.lower().strip().split(".")
    if len(parts) >= 2:
        tld = parts[-1]
        sld = parts[-2]
    else:
        tld = ""
        sld = domain.lower().strip()
    return {"sld": sld, "tld": tld}


def enrich_domain(domain: str) -> Dict[str, Any]:
    """
    Enrich a single domain with:
    - IPs
    - ASN info for the first IP (you can extend to all IPs if you like)
    - WHOIS info
    - Basic domain parts (SLD/TLD)
    """
    domain = domain.strip()
    if not domain:
        return {}

    ips = resolve_domain(domain)

    # Take first IP as representative; you can extend this if needed.
    if ips:
        asn_info = get_asn_info(ips[0])
    else:
        asn_info = {"asn": "", "asn_description": "", "asn_country": ""}

    whois_info = get_whois_info(domain)
    parts = parse_domain_parts(domain)

    record = {
        "domain": domain,
        "ips": ",".join(ips),
        "asn": asn_info.get("asn", ""),
        "asn_description": asn_info.get("asn_description", ""),
        "asn_country": asn_info.get("asn_country", ""),
        "registrar": whois_info.get("registrar", ""),
        "creation_date": whois_info.get("creation_date", ""),
        "expiration_date": whois_info.get("expiration_date", ""),
        "sld": parts.get("sld", ""),
        "tld": parts.get("tld", ""),
    }
    return record


def enrich_csv(input_csv: str, output_csv: str, domain_col: str = "domain"):
    """
    Read domains from input_csv, enrich each, and save to output_csv.
    - input_csv must have a column with domain names (default: 'domain')
    """
    df = pd.read_csv(input_csv)
    if domain_col not in df.columns:
        raise ValueError(f"Column '{domain_col}' not found in {input_csv}")

    enriched_rows = []
    for idx, row in df.iterrows():
        domain = str(row[domain_col])
        print(f"[+] Enriching {idx+1}/{len(df)}: {domain}")
        enriched = enrich_domain(domain)
        # Merge original row with enrichment, if you want to keep original columns
        merged = {**row.to_dict(), **enriched}
        enriched_rows.append(merged)

    out_df = pd.DataFrame(enriched_rows)
    out_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[✓] Saved enriched domains to {output_csv}")


def main():
    parser = argparse.ArgumentParser(description="Domain enrichment (DNS, ASN, WHOIS).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--domain", help="Single domain to enrich")
    group.add_argument("--input-csv", help="CSV file with domains")
    parser.add_argument("--output-csv", help="Output CSV for enriched results (when using --input-csv)")
    parser.add_argument("--domain-col", default="domain", help="Column name containing domains in CSV")

    args = parser.parse_args()

    if args.domain:
        rec = enrich_domain(args.domain)
        print("Enriched record:")
        for k, v in rec.items():
            print(f"{k}: {v}")

    else:
        if not args.output_csv:
            raise SystemExit("When using --input-csv, you must provide --output-csv")
        enrich_csv(args.input_csv, args.output_csv, domain_col=args.domain_col)


if __name__ == "__main__":
    main()
