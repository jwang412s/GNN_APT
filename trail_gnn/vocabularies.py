"""
Vocabulary builders for one-hot encoding categorical features.

Each vocabulary maps string values to integer indices.
Built dynamically from graph data during training, then persisted to disk.
"""

import json
import os
from collections import Counter
from typing import Optional

from . import config
from .neo4j_client import Neo4jClient


def _build_top_k_vocab(values: list[str], k: int) -> dict[str, int]:
    """Build a vocabulary of top-k values + 'other' bucket (index 0)."""
    counter = Counter(v for v in values if v)
    top_k = [item for item, _ in counter.most_common(k - 1)]
    vocab = {"__other__": 0}
    for i, val in enumerate(top_k, start=1):
        vocab[val] = i
    return vocab


# --- Fixed vocabularies ---

# ISO 3166-1 alpha-2 country codes (249 entries)
ISO_COUNTRY_CODES = [
    "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
    "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS",
    "BT","BV","BW","BY","BZ","CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN",
    "CO","CR","CU","CV","CW","CX","CY","CZ","DE","DJ","DK","DM","DO","DZ","EC","EE",
    "EG","EH","ER","ES","ET","FI","FJ","FK","FM","FO","FR","GA","GB","GD","GE","GF",
    "GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY","HK","HM",
    "HN","HR","HT","HU","ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT","JE","JM",
    "JO","JP","KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ","LA","LB","LC",
    "LI","LK","LR","LS","LT","LU","LV","LY","MA","MC","MD","ME","MF","MG","MH","MK",
    "ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ","NA",
    "NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ","OM","PA","PE","PF","PG",
    "PH","PK","PL","PM","PN","PR","PS","PT","PW","PY","QA","RE","RO","RS","RU","RW",
    "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS",
    "ST","SV","SX","SY","SZ","TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO",
    "TR","TT","TV","TW","TZ","UA","UG","UM","US","UY","UZ","VA","VC","VE","VG","VI",
    "VN","VU","WF","WS","YE","YT","ZA","ZM","ZW",
]

COUNTRY_VOCAB = {"__other__": 0}
for i, code in enumerate(ISO_COUNTRY_CODES, start=1):
    COUNTRY_VOCAB[code] = i


def build_tld_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build TLD vocabulary from Domain nodes in the graph."""
    results = client.run_query(
        "MATCH (d:Domain) WHERE d.tld IS NOT NULL RETURN d.tld AS tld"
    )
    tlds = [r["tld"] for r in results]
    return _build_top_k_vocab(tlds, config.TLD_VOCAB_SIZE)


def build_issuer_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build ASN issuer (description) vocabulary from IP nodes."""
    results = client.run_query(
        "MATCH (ip:IP) WHERE ip.asn_description IS NOT NULL "
        "RETURN ip.asn_description AS desc"
    )
    descs = [r["desc"] for r in results]
    return _build_top_k_vocab(descs, config.ISSUER_VOCAB_SIZE)


def build_server_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build Server header vocabulary from URL nodes."""
    results = client.run_query(
        "MATCH (u:URL) WHERE u.server IS NOT NULL RETURN u.server AS server"
    )
    servers = [r["server"] for r in results]
    return _build_top_k_vocab(servers, config.SERVER_VOCAB_SIZE)


def build_file_type_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build file extension vocabulary from URL nodes."""
    results = client.run_query(
        "MATCH (u:URL) WHERE u.file_extension IS NOT NULL "
        "RETURN u.file_extension AS ext"
    )
    exts = [r["ext"] for r in results]
    return _build_top_k_vocab(exts, config.FILE_TYPE_VOCAB_SIZE)


def build_http_status_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build HTTP status code vocabulary from URL nodes."""
    results = client.run_query(
        "MATCH (u:URL) WHERE u.http_status IS NOT NULL "
        "RETURN toString(u.http_status) AS status"
    )
    statuses = [r["status"] for r in results]
    return _build_top_k_vocab(statuses, config.HTTP_STATUS_VOCAB_SIZE)


def build_content_type_vocab(client: Neo4jClient) -> dict[str, int]:
    """Build Content-Type vocabulary from URL nodes."""
    results = client.run_query(
        "MATCH (u:URL) WHERE u.content_type IS NOT NULL "
        "RETURN u.content_type AS ct"
    )
    cts = [r["ct"] for r in results]
    return _build_top_k_vocab(cts, config.ENCODING_VOCAB_SIZE)


class VocabularySet:
    """Container for all vocabularies needed for feature extraction."""

    def __init__(
        self,
        tld_vocab: dict[str, int],
        country_vocab: dict[str, int],
        issuer_vocab: dict[str, int],
        server_vocab: dict[str, int],
        file_type_vocab: dict[str, int],
        http_status_vocab: dict[str, int],
        content_type_vocab: dict[str, int],
    ):
        self.tld = tld_vocab
        self.country = country_vocab
        self.issuer = issuer_vocab
        self.server = server_vocab
        self.file_type = file_type_vocab
        self.http_status = http_status_vocab
        self.content_type = content_type_vocab

    @classmethod
    def build_from_graph(cls, client: Neo4jClient) -> "VocabularySet":
        """Build all vocabularies from the current graph data."""
        return cls(
            tld_vocab=build_tld_vocab(client),
            country_vocab=COUNTRY_VOCAB,
            issuer_vocab=build_issuer_vocab(client),
            server_vocab=build_server_vocab(client),
            file_type_vocab=build_file_type_vocab(client),
            http_status_vocab=build_http_status_vocab(client),
            content_type_vocab=build_content_type_vocab(client),
        )

    def save(self, path: Optional[str] = None):
        """Persist vocabularies to JSON."""
        path = path or os.path.join(config.MODEL_DIR, "vocabularies.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "tld": self.tld,
            "country": self.country,
            "issuer": self.issuer,
            "server": self.server,
            "file_type": self.file_type,
            "http_status": self.http_status,
            "content_type": self.content_type,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "VocabularySet":
        """Load vocabularies from JSON."""
        path = path or os.path.join(config.MODEL_DIR, "vocabularies.json")
        with open(path) as f:
            data = json.load(f)
        return cls(
            tld_vocab=data["tld"],
            country_vocab=data["country"],
            issuer_vocab=data["issuer"],
            server_vocab=data["server"],
            file_type_vocab=data["file_type"],
            http_status_vocab=data["http_status"],
            content_type_vocab=data["content_type"],
        )
