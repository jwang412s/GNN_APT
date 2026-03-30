import argparse
import pandas as pd
import dns.resolver
import dns.exception

# ---------- Helpers ----------

def safe_resolve(domain, rtype, timeout=3.0):
    """
    Safely resolve a DNS record, return list of strings or [] on failure.
    """
    try:
        answers = dns.resolver.resolve(domain, rtype, lifetime=timeout)
        return answers
    except (dns.resolver.NoAnswer,
            dns.resolver.NXDOMAIN,
            dns.resolver.Timeout,
            dns.resolver.NoNameservers,
            dns.exception.DNSException):
        return []


def extract_base(hostname):
    """
    Very simple base-domain extraction:
    - takes last two labels: foo.bar
    - if only one label, returns it
    This is not perfect but good enough for clustering.
    """
    if not hostname:
        return ""
    parts = hostname.strip(".").split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    else:
        return hostname


def join_unique(values):
    """
    Join unique non-empty strings with ';'
    """
    vals = [v for v in values if v]
    if not vals:
        return ""
    return ";".join(sorted(set(vals)))


def get_dns_features(domain):
    """
    For a single domain, fetch NS, MX, SOA-based email.
    Returns dict with:
        ns_hosts, ns_base, ns_count,
        mx_hosts, mx_base, mx_count,
        soa_email
    """
    ns_hosts = []
    ns_bases = []
    mx_hosts = []
    mx_bases = []
    soa_email = ""

    # NS
    ns_answers = safe_resolve(domain, "NS")
    for rdata in ns_answers:
        host = str(rdata.target).lower()
        ns_hosts.append(host)
        ns_bases.append(extract_base(host))

    # MX
    mx_answers = safe_resolve(domain, "MX")
    for rdata in mx_answers:
        host = str(rdata.exchange).lower()
        mx_hosts.append(host)
        mx_bases.append(extract_base(host))

    # SOA
    soa_answers = safe_resolve(domain, "SOA")
    for rdata in soa_answers:
        # rname is often like 'hostmaster.example.com.'
        rname = str(rdata.rname)
        # convert to email-like: hostmaster@example.com
        parts = rname.strip(".").split(".")
        if len(parts) >= 2:
            soa_email = parts[0] + "@" + ".".join(parts[1:])
        else:
            soa_email = rname
        break  # only take first SOA

    return {
        "ns_hosts": join_unique(ns_hosts),
        "ns_base": join_unique(ns_bases),
        "ns_count": len(set(ns_hosts)),
        "mx_hosts": join_unique(mx_hosts),
        "mx_base": join_unique(mx_bases),
        "mx_count": len(set(mx_hosts)),
        "soa_email": soa_email,
    }


def estimate_ip_count(row):
    """
    If you already have an 'ips' column with comma-separated IPs,
    count them. Otherwise return None.
    """
    ips = row.get("ips", "")
    if isinstance(ips, str) and ips.strip():
        return len([p for p in ips.split(",") if p.strip()])
    return None


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(
        description="Add DNS-based features (NS, MX, SOA) to an enriched domains CSV."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input CSV file (must have a 'domain' column).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV file with extra DNS feature columns.",
    )
    args = parser.parse_args()

    print(f"[*] Loading {args.input} ...")
    df = pd.read_csv(args.input)

    if "domain" not in df.columns:
        raise ValueError(f"'domain' column not found in {args.input}. Columns: {list(df.columns)}")

    # Prepare new columns
    ns_hosts_list = []
    ns_base_list = []
    ns_count_list = []
    mx_hosts_list = []
    mx_base_list = []
    mx_count_list = []
    soa_email_list = []
    ip_count_list = []

    total = len(df)
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        domain = str(row["domain"]).strip()
        if not domain:
            # empty row
            ns_hosts_list.append("")
            ns_base_list.append("")
            ns_count_list.append(0)
            mx_hosts_list.append("")
            mx_base_list.append("")
            mx_count_list.append(0)
            soa_email_list.append("")
            ip_count_list.append(estimate_ip_count(row))
            continue

        # Clean domain if wrapped like 'example[.]com'
        domain_clean = domain.replace("[.]", ".").replace("(.)", ".")

        if i % 50 == 0:
            print(f"    [*] {i}/{total} domains processed...")

        features = get_dns_features(domain_clean)

        ns_hosts_list.append(features["ns_hosts"])
        ns_base_list.append(features["ns_base"])
        ns_count_list.append(features["ns_count"])
        mx_hosts_list.append(features["mx_hosts"])
        mx_base_list.append(features["mx_base"])
        mx_count_list.append(features["mx_count"])
        soa_email_list.append(features["soa_email"])
        ip_count_list.append(estimate_ip_count(row))

    # Attach to dataframe
    df["ns_hosts"] = ns_hosts_list
    df["ns_base"] = ns_base_list
    df["ns_count"] = ns_count_list
    df["mx_hosts"] = mx_hosts_list
    df["mx_base"] = mx_base_list
    df["mx_count"] = mx_count_list
    df["soa_email"] = soa_email_list

    # Only add ip_count if not already present
    if "ip_count" not in df.columns:
        df["ip_count"] = ip_count_list

    print(f"[*] Saving to {args.output} ...")
    df.to_csv(args.output, index=False)
    print("[*] Done.")


if __name__ == "__main__":
    main()
