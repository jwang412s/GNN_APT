"""
IOC enrichment functions for the TRAIL knowledge graph.

Ports and extends functions from:
- domain_enrichment.py (resolve_domain, get_asn_info)
- add_dns_features.py (safe_resolve, get_dns_features)

Adds: Shannon entropy, full 9-type DNS counting, NXDOMAIN detection,
URL parsing with HTTP HEAD, IP enrichment.
"""

import math
import re
import socket
from typing import Optional
from urllib.parse import urlparse

import dns.resolver
import dns.exception
import requests
import tldextract
from ipwhois import IPWhois

from . import config


# ---------------------------------------------------------------------------
# Utility: Shannon entropy
# ---------------------------------------------------------------------------

def shannon_entropy(s: str) -> float:
    """Compute Shannon entropy of a string."""
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


# ---------------------------------------------------------------------------
# DNS resolution helpers (ported from add_dns_features.py)
# ---------------------------------------------------------------------------

def safe_resolve(domain: str, rtype: str, timeout: float = config.DNS_TIMEOUT):
    """Safely resolve a DNS record type. Returns answer set or empty list."""
    try:
        answers = dns.resolver.resolve(domain, rtype, lifetime=timeout)
        return answers
    except (
        dns.resolver.NoAnswer,
        dns.resolver.NXDOMAIN,
        dns.resolver.Timeout,
        dns.resolver.NoNameservers,
        dns.exception.DNSException,
    ):
        return []


def check_nxdomain(domain: str, timeout: float = config.DNS_TIMEOUT) -> bool:
    """Check if a domain returns NXDOMAIN (does not exist)."""
    try:
        dns.resolver.resolve(domain, "A", lifetime=timeout)
        return False
    except dns.resolver.NXDOMAIN:
        return True
    except (
        dns.resolver.NoAnswer,
        dns.resolver.Timeout,
        dns.resolver.NoNameservers,
        dns.exception.DNSException,
    ):
        # NoAnswer means the domain exists but has no A record — not NXDOMAIN.
        # Timeout/NoNameservers are inconclusive; default to not-NXDOMAIN.
        return False


# ---------------------------------------------------------------------------
# Domain enrichment
# ---------------------------------------------------------------------------

def resolve_domain_ips(domain: str) -> list[str]:
    """Resolve domain to A records (IPv4). Returns list of IP strings."""
    ips = set()
    try:
        answers = dns.resolver.resolve(domain, "A")
        for rdata in answers:
            ips.add(rdata.address)
    except Exception:
        try:
            _, _, addr_list = socket.gethostbyname_ex(domain)
            ips.update(addr_list)
        except Exception:
            pass
    return sorted(ips)


def get_asn_info(ip: str) -> dict:
    """Fetch ASN info for an IP via RDAP. Returns {asn, asn_description, country}."""
    try:
        obj = IPWhois(ip)
        res = obj.lookup_rdap(asn_methods=["whois", "http"])
        return {
            "asn": res.get("asn", "") or "",
            "asn_description": res.get("asn_description", "") or "",
            "country": res.get("asn_country_code", "") or "",
        }
    except Exception:
        return {"asn": "", "asn_description": "", "country": ""}


def get_dns_record_counts(domain: str) -> dict:
    """
    Query all 9 DNS record types required by the TRAIL paper.
    Returns count of unique records per type.
    """
    record_types = ["A", "AAAA", "MX", "NS", "SOA", "TXT", "CNAME", "PTR", "SRV"]
    counts = {}
    for rtype in record_types:
        answers = safe_resolve(domain, rtype)
        counts[f"{rtype.lower()}_count"] = len(list(answers)) if answers else 0
    return counts


def enrich_domain(domain: str) -> dict:
    """
    Full domain enrichment for the TRAIL knowledge graph.
    Returns all properties needed for the Domain node schema.
    """
    domain = domain.strip().lower().replace("[.]", ".").replace("(.)", ".")
    if not domain:
        return _empty_domain_response(domain)

    # TLD extraction
    extracted = tldextract.extract(domain)
    tld = extracted.suffix or ""

    # Lexical features
    length = len(domain)
    digit_count = sum(c.isdigit() for c in domain)
    period_count = domain.count(".")
    entropy = shannon_entropy(domain)

    # NXDOMAIN check
    is_nxdomain = check_nxdomain(domain)

    # DNS record counts (all 9 types)
    dns_counts = get_dns_record_counts(domain)

    # Active period from passive DNS is computed in n8n from OTX data.
    # We set a default here; n8n will override with actual pDNS timestamps.
    active_period_days = 0

    # IP resolution + ASN info
    ips = resolve_domain_ips(domain)
    if ips:
        asn_info = get_asn_info(ips[0])
    else:
        asn_info = {"asn": "", "asn_description": "", "country": ""}

    return {
        "domain": domain,
        "tld": tld,
        "length": length,
        "digit_count": digit_count,
        "period_count": period_count,
        "entropy": round(entropy, 4),
        "is_nxdomain": is_nxdomain,
        "active_period_days": active_period_days,
        **dns_counts,
        "country": asn_info["country"],
        "asn": asn_info["asn"],
        "asn_description": asn_info["asn_description"],
    }


def _empty_domain_response(domain: str) -> dict:
    return {
        "domain": domain,
        "tld": "",
        "length": 0,
        "digit_count": 0,
        "period_count": 0,
        "entropy": 0.0,
        "is_nxdomain": False,
        "active_period_days": 0,
        "a_count": 0, "aaaa_count": 0, "mx_count": 0,
        "ns_count": 0, "soa_count": 0, "txt_count": 0,
        "cname_count": 0, "ptr_count": 0, "srv_count": 0,
        "country": "", "asn": "", "asn_description": "",
    }


# ---------------------------------------------------------------------------
# IP enrichment
# ---------------------------------------------------------------------------

def enrich_ip(ip: str) -> dict:
    """
    Full IP enrichment for the TRAIL knowledge graph.
    Returns country code, ASN number, and ASN description (issuer).
    """
    ip = ip.strip()
    if not ip:
        return {"ip": ip, "country": "", "asn": "", "asn_description": ""}

    asn_info = get_asn_info(ip)
    return {
        "ip": ip,
        "country": asn_info["country"],
        "asn": asn_info["asn"],
        "asn_description": asn_info["asn_description"],
    }


# ---------------------------------------------------------------------------
# URL enrichment
# ---------------------------------------------------------------------------

def enrich_url(url: str) -> dict:
    """
    Full URL enrichment for the TRAIL knowledge graph.
    Extracts lexical features, performs HTTP HEAD for server features.
    """
    raw_url = url.strip()
    if not raw_url:
        return _empty_url_response(raw_url)

    # Defang common URL obfuscation
    clean_url = raw_url.replace("hxxp", "http").replace("[.]", ".").replace("(.)", ".")

    # Parse URL
    parsed = urlparse(clean_url if "://" in clean_url else f"http://{clean_url}")
    extracted = tldextract.extract(clean_url)

    host = parsed.hostname or ""
    path = parsed.path or ""
    tld = extracted.suffix or ""
    extracted_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.suffix else extracted.domain

    # Lexical features
    length = len(raw_url)
    digit_count = sum(c.isdigit() for c in raw_url)
    special_char_count = sum(not c.isalnum() and c not in ".-_/:?" for c in raw_url)
    path_depth = len([p for p in path.split("/") if p])
    has_query = bool(parsed.query)
    has_fragment = bool(parsed.fragment)
    entropy = shannon_entropy(raw_url)

    # File extension
    file_extension = ""
    path_parts = path.rsplit(".", 1)
    if len(path_parts) == 2 and len(path_parts[1]) <= 10:
        file_extension = path_parts[1].lower().split("?")[0].split("#")[0]

    # HTTP HEAD for server features
    http_status = None
    content_type = ""
    server = ""
    head_failed = True
    resolved_ip = None

    try:
        resp = requests.head(
            clean_url,
            timeout=config.HTTP_HEAD_TIMEOUT,
            allow_redirects=True,
            verify=False,
        )
        http_status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        server = resp.headers.get("Server", "")
        head_failed = False
    except Exception:
        pass

    # Resolve domain to IP
    ips = resolve_domain_ips(host) if host else []
    if ips:
        resolved_ip = ips[0]

    return {
        "url": raw_url,
        "extracted_domain": extracted_domain,
        "path": path,
        "tld": tld,
        "length": length,
        "digit_count": digit_count,
        "special_char_count": special_char_count,
        "path_depth": path_depth,
        "has_query": has_query,
        "has_fragment": has_fragment,
        "entropy": round(entropy, 4),
        "file_extension": file_extension,
        "http_status": http_status,
        "content_type": content_type,
        "server": server,
        "head_failed": head_failed,
        "resolved_ip": resolved_ip,
    }


def _empty_url_response(url: str) -> dict:
    return {
        "url": url,
        "extracted_domain": "",
        "path": "",
        "tld": "",
        "length": 0,
        "digit_count": 0,
        "special_char_count": 0,
        "path_depth": 0,
        "has_query": False,
        "has_fragment": False,
        "entropy": 0.0,
        "file_extension": "",
        "http_status": None,
        "content_type": "",
        "server": "",
        "head_failed": True,
        "resolved_ip": None,
    }
