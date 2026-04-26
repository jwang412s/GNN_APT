"""
Tier 1 OTX enrichment primitives: ASN lookup, forward pDNS, reverse pDNS.

Used by both the fresh-collection pipeline (collect_otx.py) and the
graph-backfill script (enrich_graph.py). The functions here are pure —
they perform HTTP calls and return normalized dicts — so callers are
responsible for Neo4j writes and retries beyond HTTP transport.

Key rotation:
    All enrichment functions accept either a single API key string OR a
    KeyPool. Multiple keys are rotated round-robin per request and a key
    that returns 429 is cooled down for 30 s while other keys keep
    serving. This roughly doubles throughput when two keys are supplied.

Normalization rules (what this module promises callers):
  - get_ip_general(ip, keys)
      → {"asn_number": int|None, "asn_name": str, "country": str}
  - get_forward_pdns(domain, keys)
      → list[{"ip": str, "record_type": str, "first": str, "last": str}]
  - get_reverse_pdns(ip, keys)
      → list[{"domain": str, "record_type": str, "first": str, "last": str}]

`keys` may be either a KeyPool or a single API-key string (wrapped into
a pool-of-one internally).
"""

from __future__ import annotations

import re
import threading
import time
import requests

OTX_BASE = "https://otx.alienvault.com/api/v1"

# ASN string pattern OTX returns, e.g. "AS13335 Cloudflare, Inc."
_ASN_RE = re.compile(r"^AS(\d+)\s*(.*)$", re.IGNORECASE)


class OTXTransientError(Exception):
    """Raised when every retry attempt hits a transient failure (timeout / 5xx /
    all keys cooling). Callers should record the target for later retry instead
    of treating it as "no data". HTTP 404 is NOT transient — it returns None."""


class KeyPool:
    """
    Round-robin rotator over one or more OTX API keys.

    A key that hits a 429 response is marked cooling for `cooldown_s`
    seconds; requests route to the next available key. If every key is
    cooling, the caller sleeps until the earliest one recovers.

    Single-key usage: `pool = KeyPool([one_key])`. The rotation is a
    no-op, but the same call-site code works for 1 or N keys.
    """

    def __init__(self, keys: list[str], cooldown_s: float = 30.0) -> None:
        cleaned = [k.strip() for k in keys if k and k.strip()]
        if not cleaned:
            raise ValueError("KeyPool requires at least one non-empty API key")
        self._keys = cleaned
        self._idx = 0
        self._cooldowns: dict[str, float] = {}
        self._cooldown_s = cooldown_s
        # Thread-safe: next_key() and cooldown() may be called concurrently
        # from worker threads in the ThreadPoolExecutor path.
        self._lock = threading.Lock()
        # Observability: total 429s seen across all keys, and total times
        # next_key() had to sleep because every key was cooling. Both are
        # monotonic counters — callers snapshot and diff for rate views.
        self._total_429 = 0
        self._total_all_cooling_waits = 0
        self._total_cooling_wait_s = 0.0

    @classmethod
    def coerce(cls, keys_or_key: "str | KeyPool") -> "KeyPool":
        """Accept either a str (single key) or a KeyPool; always return a pool."""
        if isinstance(keys_or_key, KeyPool):
            return keys_or_key
        return cls([keys_or_key])

    def __len__(self) -> int:
        return len(self._keys)

    def next_key(self, max_wait_s: float | None = None) -> str | None:
        """Return the next available key, waiting if all are cooling down.

        If `max_wait_s` is given, the total time spent sleeping on all-cooling
        waits is bounded by that value; if exceeded, returns None so the
        caller can fail fast instead of burning worker budget on cooldowns.
        """
        n = len(self._keys)
        budget = max_wait_s  # None = unlimited (preserve old behavior)
        while True:
            with self._lock:
                now = time.time()
                # Try each key starting from self._idx
                for _ in range(n):
                    k = self._keys[self._idx]
                    self._idx = (self._idx + 1) % n
                    if self._cooldowns.get(k, 0.0) <= now:
                        return k
                # Every key is cooling
                if budget is not None and budget <= 0:
                    return None
                wait = max(0.5, min(self._cooldowns.values()) - now)
                if budget is not None:
                    wait = min(wait, budget)
                self._total_all_cooling_waits += 1
                self._total_cooling_wait_s += wait
            time.sleep(wait)
            if budget is not None:
                budget -= wait

    def cooldown(self, key: str, seconds: float | None = None) -> None:
        """Mark `key` unavailable for `seconds` (default self._cooldown_s)."""
        with self._lock:
            self._cooldowns[key] = time.time() + (seconds if seconds is not None else self._cooldown_s)
            self._total_429 += 1

    def stats(self) -> dict:
        """Snapshot of pool counters. Cheap; safe to call from any thread."""
        with self._lock:
            now = time.time()
            cooling = sum(1 for t in self._cooldowns.values() if t > now)
            return {
                "total_429": self._total_429,
                "all_cooling_waits": self._total_all_cooling_waits,
                "cooling_wait_s": round(self._total_cooling_wait_s, 1),
                "keys_cooling_now": cooling,
                "keys_total": len(self._keys),
            }


def _get(url: str, pool: KeyPool, timeout: int = 5, retries: int = 2,
         base_delay: float = 1.0, params: dict | None = None,
         max_429_rotations: int = 3,
         max_wall_s: float | None = None) -> dict | None:
    """
    GET with exponential backoff on 5xx + transport errors. Uses `pool`
    for per-request key rotation.

    Retry accounting:
      - 429 does NOT consume a retry (rotates to the next key via
        pool.cooldown), but IS bounded by `max_429_rotations`.
      - Timeout / 5xx DO consume a retry.

    Wall-clock bound:
      - `max_wall_s` caps total time in this function across all retries
        AND cooldown-waits. Default: max(timeout * 2, 12s). This prevents
        the nightmare case where 4 workers all 429 at once, every key is
        cooling for 30s, and each worker's single `_get` call burns 30-60s
        waiting for keys to thaw before bailing.

    Return semantics:
      - 200  → parsed JSON dict
      - 404 / permanent 4xx → None
      - exhausted / deadline / rotation cap → raises OTXTransientError
    """
    if max_wall_s is None:
        max_wall_s = max(timeout * 2, 12.0)
    deadline = time.time() + max_wall_s

    attempts_left = max(retries, 1)
    attempt_idx = 0
    rotations_429 = 0
    while attempts_left > 0:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise OTXTransientError(f"wall-clock {max_wall_s:.1f}s: {url}")
        key = pool.next_key(max_wait_s=remaining)
        if key is None:
            # All keys cooling past the deadline. Fail fast.
            raise OTXTransientError(f"all keys cooling past deadline: {url}")
        headers = {"X-OTX-API-KEY": key}
        # Don't let a single HTTP call overrun the wall-clock budget.
        req_timeout = min(timeout, max(1.0, deadline - time.time()))
        try:
            r = requests.get(url, headers=headers, timeout=req_timeout, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                pool.cooldown(key)
                rotations_429 += 1
                if rotations_429 >= max_429_rotations:
                    raise OTXTransientError(
                        f"429 rotation cap ({max_429_rotations}) hit: {url}"
                    )
                continue
            if r.status_code in (502, 503, 504):
                attempts_left -= 1
                if attempts_left > 0:
                    # Don't sleep past the deadline.
                    backoff = base_delay * (2 ** attempt_idx)
                    time.sleep(min(backoff, max(0.0, deadline - time.time())))
                    attempt_idx += 1
                continue
            # 4xx other than 404/429 — treat as permanent for this call
            return None
        except (requests.Timeout, requests.ConnectionError):
            attempts_left -= 1
            if attempts_left > 0:
                backoff = base_delay * (2 ** attempt_idx)
                time.sleep(min(backoff, max(0.0, deadline - time.time())))
                attempt_idx += 1
    raise OTXTransientError(f"retries exhausted: {url}")


def parse_asn(asn_string: str) -> tuple[int | None, str]:
    """
    Parse OTX's ASN string "AS12345 Example Corp" into (12345, "Example Corp").
    Returns (None, "") if unparseable.
    """
    if not asn_string:
        return None, ""
    m = _ASN_RE.match(asn_string.strip())
    if not m:
        return None, ""
    return int(m.group(1)), m.group(2).strip()


def get_ip_general(ip: str, keys: "str | KeyPool") -> dict:
    """
    Fetch an IP's general metadata from OTX.

    Returns a dict with keys: asn_number (int|None), asn_name (str), country (str).
    On failure, returns all-empty dict — callers should treat it as no-data.
    """
    pool = KeyPool.coerce(keys)
    data = _get(f"{OTX_BASE}/indicators/IPv4/{ip}/general", pool)
    if not data:
        return {"asn_number": None, "asn_name": "", "country": ""}
    asn_num, asn_name = parse_asn(data.get("asn") or "")
    return {
        "asn_number": asn_num,
        "asn_name": asn_name,
        "country": (data.get("country_code") or "").upper(),
    }


def get_forward_pdns(domain: str, keys: "str | KeyPool", limit: int = 50) -> list[dict]:
    """
    Forward pDNS: domain → list of IPs it has historically resolved to.

    Returns at most `limit` records. Empty list on failure / no data.
    Each record: {"ip": str, "record_type": "A"|"AAAA"|..., "first": str, "last": str}
    """
    pool = KeyPool.coerce(keys)
    # Single 10s attempt. If OTX is slow for this domain, a 2nd try won't
    # help — both keys hit the same backend. 429s still rotate keys
    # without consuming the attempt.
    data = _get(
        f"{OTX_BASE}/indicators/domain/{domain}/passive_dns",
        pool, timeout=10, retries=1, params={"limit": limit},
    )
    if not data:
        return []
    out = []
    for rec in data.get("passive_dns", [])[:limit]:
        addr = rec.get("address") or rec.get("hostname")
        rtype = rec.get("record_type") or ""
        if not addr or rtype.upper() not in ("A", "AAAA"):
            continue
        out.append({
            "ip": addr,
            "record_type": rtype.upper(),
            "first": rec.get("first") or "",
            "last": rec.get("last") or "",
        })
    return out


def get_reverse_pdns(ip: str, keys: "str | KeyPool", limit: int = 10,
                     timeout: int = 10) -> list[dict]:
    """
    Reverse pDNS: IP → list of domains that have historically resolved to it.

    This is the enrichment the TRAIL paper relies on to get 75% of nodes
    as "secondary IOCs" and push 2-hop event connectivity past 85%.

    The default limit (10) matches where paper-style benefit saturates —
    the top-N shared-infra domains per IP carry most of the cross-event
    linking signal; additional domains are largely benign co-residents.

    `timeout` is exposed so callers can run a fast first pass with a
    tight ceiling (10s) and a dedicated shared-infra retry pass with
    a relaxed ceiling (e.g. 30s). Single attempt either way — retries
    on timeout don't help because both keys hit the same slow backend.

    Returns at most `limit` records. Each record:
      {"domain": str, "record_type": "A"|"AAAA", "first": str, "last": str}
    """
    pool = KeyPool.coerce(keys)
    # Server-side limit avoids megabyte-scale responses for shared-infra IPs
    # (GitHub Pages, Cloudflare, AWS) whose full pDNS table is 1000s of rows.
    data = _get(
        f"{OTX_BASE}/indicators/IPv4/{ip}/passive_dns",
        pool, timeout=timeout, retries=1, params={"limit": limit},
    )
    if not data:
        return []
    out = []
    for rec in data.get("passive_dns", [])[:limit]:
        host = rec.get("hostname") or rec.get("address")
        rtype = (rec.get("record_type") or "").upper()
        if not host or rtype not in ("A", "AAAA"):
            continue
        if host.replace(".", "").isdigit():
            continue
        out.append({
            "domain": host.lower().strip("."),
            "record_type": rtype,
            "first": rec.get("first") or "",
            "last": rec.get("last") or "",
        })
    return out


def key_pool_from_env() -> KeyPool:
    """
    Build a KeyPool from the environment.

    Priority:
      1. $OTX_API_KEYS  — comma-separated list (preferred for multi-key runs)
      2. $OTX_API_KEY   — single-key fallback

    Raises ValueError if neither is set.
    """
    import os
    multi = os.environ.get("OTX_API_KEYS", "").strip()
    if multi:
        return KeyPool([k for k in multi.split(",")])
    single = os.environ.get("OTX_API_KEY", "").strip()
    if single:
        return KeyPool([single])
    raise ValueError(
        "Neither OTX_API_KEYS (comma-separated) nor OTX_API_KEY is set."
    )
