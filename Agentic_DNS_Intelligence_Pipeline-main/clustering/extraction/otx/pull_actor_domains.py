import os
import json
import time
import pathlib
import requests
from dotenv import load_dotenv

# --- paths & env ---
BASE = pathlib.Path(r"C:\ti-otx")
OUT_DIR = BASE / "actor_domains"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# load .env from C:\ti-otx\.env
load_dotenv(BASE / ".env")
OTX_KEY = os.getenv("OTX_API_KEY")

if not OTX_KEY:
    raise RuntimeError("No OTX_API_KEY found in C:\\ti-otx\\.env")

session = requests.Session()
session.headers.update({
    "X-OTX-API-KEY": OTX_KEY,
    "User-Agent": "cmpt-otx-actor-collector/1.0"
})

def iter_pulses(limit_pages=5, per_page=50):
    """
    Yield pulse JSONs from your 'subscribed' feed.

    You can later switch to other endpoints if needed,
    but this is a good start to build an actor → domains map.
    """
    url = "https://otx.alienvault.com/api/v1/pulses/subscribed"
    page = 1

    while page <= limit_pages:
        params = {"page": page, "limit": per_page}
        print(f"[OTX] Fetching pulses page {page}...")
        r = session.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        results = data.get("results", [])
        if not results:
            break

        for pulse in results:
            yield pulse

        if len(results) < per_page:
            break

        page += 1
        time.sleep(1)  # be nice to the API

def build_actor_domain_map(max_pages=5):
    actor_map = {}
    pulse_count = 0

    for pulse in iter_pulses(limit_pages=max_pages):
        pulse_count += 1

        adversary = (pulse.get("adversary") or "").strip()
        if not adversary:
            # we only care about pulses that explicitly name an actor
            continue

        pulse_id = pulse.get("id")
        indicators = pulse.get("indicators", []) or []

        domain_values = [
            ind["indicator"]
            for ind in indicators
            if ind.get("type") in ("domain", "hostname")
        ]

        if not domain_values:
            continue

        if adversary not in actor_map:
            actor_map[adversary] = {
                "pulses": set(),
                "domains": set(),
            }

        actor_entry = actor_map[adversary]
        if pulse_id:
            actor_entry["pulses"].add(pulse_id)
        actor_entry["domains"].update(domain_values)

    # convert sets → lists for JSON
    actor_map_jsonable = {}
    for actor, data in actor_map.items():
        actor_map_jsonable[actor] = {
            "pulses": sorted(list(data["pulses"])),
            "domains": sorted(list(data["domains"])),
        }

    return actor_map_jsonable, pulse_count

if __name__ == "__main__":
    actor_map, total_pulses = build_actor_domain_map(max_pages=5)

    out_file = OUT_DIR / "actor_domains_from_pulses.json"
    payload = {
        "source": "otx_pulses_subscribed",
        "pages_scanned": 5,
        "total_pulses_seen": total_pulses,
        "actors": actor_map,
    }

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {out_file}")
    print(f"Found {len(actor_map)} actors with at least one domain.")

