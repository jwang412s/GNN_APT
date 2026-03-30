from dotenv import load_dotenv
import os
load_dotenv(dotenv_path=r"C:\ti-sources\.env")
OTX_KEY = os.getenv("OTX_API_KEY")

import pathlib

DOMAINS_FILE = pathlib.Path(r"C:\ti-otx\actor_domains\domains_for_enrichment.txt")

with DOMAINS_FILE.open("r", encoding="utf-8") as f:
    DOMAINS = [line.strip() for line in f if line.strip()]

import json, time, pathlib, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SAMPLES = pathlib.Path(r"C:\ti-sources\samples")
SAMPLES.mkdir(parents=True, exist_ok=True)

DOMAINS = ["example.com", "microsoft.com"]
TEST_IPS = ["8.8.8.8", "1.1.1.1"]  # Google DNS, Cloudflare DNS

# --- session with retries ---
def session_with_retries(total=3, backoff=0.5, status_forcelist=(429, 500, 502, 503, 504)):
    s = requests.Session()
    retry = Retry(
        total=total,
        read=total,
        connect=total,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

SESSION = session_with_retries()

def fetch_json(url, timeout=20, headers=None):
    t0 = time.time()
    hdrs = {"User-Agent":"ti-prototype/1.0"}
    if headers:
        hdrs.update(headers)
    r = SESSION.get(url, timeout=timeout, headers=hdrs)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        text = r.text
        try:
            data = json.loads(text)
        except Exception:
            lines = [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]
            data = lines if lines else {"raw": text}
    dur = round(time.time()-t0, 2)
    return data, dur

def save_sample(name, data):
    (SAMPLES / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

def run_rdap(domain):
    try:
        url = f"https://rdap.verisign.com/com/v1/domain/{domain}"
        data, dur = fetch_json(url, timeout=20)
        save_sample(f"rdap_{domain}", data)
        print(f"[RDAP]    {domain:17} -> ok in {dur}s")
    except Exception as e:
        print(f"[RDAP]    {domain:17} -> ERROR: {e}")

def run_crtsh(domain):
    try:
        # crt.sh can be slow; give it more time and let retries do their thing
        url = f"https://crt.sh/?q={domain}&output=json"
        data, dur = fetch_json(url, timeout=45)
        save_sample(f"crtsh_{domain}", data)
        rows = len(data) if isinstance(data, list) else 1
        print(f"[crt.sh]  {domain:17} -> {rows} rows in {dur}s")
    except Exception as e:
        print(f"[crt.sh]  {domain:17} -> ERROR: {e}")

def run_bgpview(ip):
    try:
        url = f"https://api.bgpview.io/ip/{ip}"
        data, dur = fetch_json(url, timeout=20)
        save_sample(f"bgpview_{ip.replace('.','_')}", data)
        asn = None
        # try direct
        asn = (data.get("data",{}).get("asn") or {}).get("asn")
        # fallback: first prefix->asn
        if not asn:
            prefixes = data.get("data",{}).get("prefixes") or []
            if prefixes and isinstance(prefixes, list):
                asn = ((prefixes[0].get("asn") or {}).get("asn"))
        print(f"[BGPView] {ip:15} -> ASN {asn} in {dur}s")
    except Exception as e:
        print(f"[BGPView] {ip:15} -> ERROR: {e}")

def run_ipapi(ip):
    try:
        url = f"https://ipapi.co/{ip}/json/"
        data, dur = fetch_json(url, timeout=20)
        save_sample(f"ipapi_{ip.replace('.','_')}", data)
        country = data.get("country_name")
        print(f"[ipapi]   {ip:15} -> {country} in {dur}s")
    except Exception as e:
        print(f"[ipapi]   {ip:15} -> ERROR: {e}")

def run_maxmind(ip):
    try:
        from geoip2.database import Reader
        db_path = r"C:\ti-sources\GeoLite2-City.mmdb"
        reader = Reader(db_path)
        rec = reader.city(ip)
        data = {
            "ip": ip,
            "country": (rec.country.names.get("en") if rec.country and rec.country.names else rec.country.iso_code),
            "region": (rec.subdivisions.most_specific.names.get("en") if rec.subdivisions and rec.subdivisions.most_specific and rec.subdivisions.most_specific.names else None),
            "city": (rec.city.names.get("en") if rec.city and rec.city.names else None),
            "lat": rec.location.latitude,
            "lon": rec.location.longitude

        }
        reader.close()
        save_sample(f"maxmind_{ip.replace('.','_')}", data)
        print(f"[maxmind] {ip:15} -> {data['country']}, {data['city']}")
    except Exception as e:
        print(f"[maxmind] {ip:15} -> ERROR: {e}")

def run_otx_general(domain):
    if not OTX_KEY:
        print(f"[OTX gen] {domain:17} -> SKIP (no API key in .env)")
        return
    try:
        url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/general"
        headers = {"X-OTX-API-KEY": OTX_KEY}
        data, dur = fetch_json(url, timeout=20, headers=headers)
        save_sample(f"otx_general_{domain}", data)
        pulses = (data.get("pulse_info", {}) or {}).get("count")
        rep = data.get("reputation")
        print(f"[OTX gen] {domain:17} -> pulses={pulses}, rep={rep} in {dur}s")
    except Exception as e:
        print(f"[OTX gen] {domain:17} -> ERROR: {e}")

def run_otx_urls(domain):
    if not OTX_KEY:
        print(f"[OTX urls]{domain:17} -> SKIP (no API key in .env)")
        return
    try:
        url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/url_list?limit=25"
        headers = {"X-OTX-API-KEY": OTX_KEY}
        data, dur = fetch_json(url, timeout=20, headers=headers)
        save_sample(f"otx_urls_{domain}", data)
        urls = len(((data.get("result") or {}).get("url_list") or []))
        print(f"[OTX urls]{domain:17} -> {urls} urls in {dur}s")
    except Exception as e:
        print(f"[OTX urls]{domain:17} -> ERROR: {e}")


if __name__ == "__main__":
    print("== Probing domains ==")
    for d in DOMAINS:
        run_rdap(d)
        # be a good citizen: small pause between calls
        time.sleep(0.3)
        run_crtsh(d)
        time.sleep(0.3)
        run_otx_general(d)
        time.sleep(0.3)
        run_otx_urls(d)
        time.sleep(0.3)


    print("== Probing IPs ==")
    for ip in TEST_IPS:
        run_bgpview(ip)
        time.sleep(0.3)
        # run_ipapi(ip)
        run_maxmind(ip)         # local DB lookup
        time.sleep(0.3)

    print("\nSamples saved to C:\\ti-sources\\samples")
