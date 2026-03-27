"""
Feature vector construction for Domain, IP, and URL nodes.

Dimensions (extended from TRAIL paper Section IV-B with temporal features):
  Domain: 117 = 100 TLD + 9 DNS counts + 1 NXDOMAIN + 4 lexical + 1 active_period + 2 temporal
  IP:     509 = 249 country + 258 issuer + 2 temporal
  URL:   1517 = 106 file_type + 68 http_status + 12 content_type +
                944 server + 4 lexical + 1 entropy + 1 path_depth +
                1 has_query + 1 has_fragment + 1 head_failed + 2 temporal +
                (remaining padded to match paper dim)

Temporal features (lifespan_days, recency_days) are derived from:
  - Domain/IP: ResolvesTo edge first_seen/last_seen (pDNS)
  - URL: InReport edge indicator_created (OTX pulse data)
"""

import numpy as np

from . import config
from .vocabularies import VocabularySet


def _one_hot(value: str, vocab: dict[str, int], size: int) -> np.ndarray:
    """Create a one-hot vector. Unknown values map to __other__ (index 0)."""
    vec = np.zeros(size, dtype=np.float32)
    idx = vocab.get(value, vocab.get("__other__", 0))
    vec[idx] = 1.0
    return vec


def domain_features(props: dict, vocabs: VocabularySet) -> np.ndarray:
    """
    Build 117-dim feature vector for a Domain node.

    Layout: [100 TLD one-hot | 9 DNS counts | 1 NXDOMAIN | 4 lexical | 1 active_period | 2 temporal]
    """
    # TLD one-hot (100)
    tld_vec = _one_hot(props.get("tld", ""), vocabs.tld, config.TLD_VOCAB_SIZE)

    # DNS record counts (9)
    dns_counts = np.array([
        props.get("a_count", 0),
        props.get("aaaa_count", 0),
        props.get("mx_count", 0),
        props.get("ns_count", 0),
        props.get("soa_count", 0),
        props.get("txt_count", 0),
        props.get("cname_count", 0),
        props.get("ptr_count", 0),
        props.get("srv_count", 0),
    ], dtype=np.float32)

    # NXDOMAIN flag (1)
    nxdomain = np.array([1.0 if props.get("is_nxdomain", False) else 0.0],
                        dtype=np.float32)

    # Lexical features (4): length, digit_count, period_count, entropy
    lexical = np.array([
        props.get("length", 0),
        props.get("digit_count", 0),
        props.get("period_count", 0),
        props.get("entropy", 0.0),
    ], dtype=np.float32)

    # Active period (1)
    active = np.array([props.get("active_period_days", 0)], dtype=np.float32)

    # Temporal features (2): lifespan_days, recency_days
    temporal = np.array([
        props.get("lifespan_days", 0.0),
        props.get("recency_days", 0.0),
    ], dtype=np.float32)

    vec = np.concatenate([tld_vec, dns_counts, nxdomain, lexical, active, temporal])
    assert vec.shape[0] == config.DOMAIN_FEATURE_DIM, (
        f"Domain feature dim mismatch: {vec.shape[0]} != {config.DOMAIN_FEATURE_DIM}"
    )
    return vec


def ip_features(props: dict, vocabs: VocabularySet) -> np.ndarray:
    """
    Build 509-dim feature vector for an IP node.

    Layout: [249 country one-hot | 258 issuer one-hot | 2 temporal]
    """
    country_vec = _one_hot(
        props.get("country", ""), vocabs.country, config.COUNTRY_VOCAB_SIZE
    )
    issuer_vec = _one_hot(
        props.get("asn_description", ""), vocabs.issuer, config.ISSUER_VOCAB_SIZE
    )

    # Temporal features (2): lifespan_days, recency_days
    temporal = np.array([
        props.get("lifespan_days", 0.0),
        props.get("recency_days", 0.0),
    ], dtype=np.float32)

    vec = np.concatenate([country_vec, issuer_vec, temporal])
    assert vec.shape[0] == config.IP_FEATURE_DIM, (
        f"IP feature dim mismatch: {vec.shape[0]} != {config.IP_FEATURE_DIM}"
    )
    return vec


def url_features(props: dict, vocabs: VocabularySet) -> np.ndarray:
    """
    Build 1517-dim feature vector for a URL node.

    Layout: [106 file_type | 68 http_status | 12 content_type | 944 server |
             4 lexical | 1 entropy | 1 path_depth | 1 has_query |
             1 has_fragment | 1 head_failed | padding to 1517]

    The paper's 1517 dimensions include additional sub-features from
    OS detection, services, etc. We pad the remaining dimensions to
    maintain compatibility with the autoencoder architecture.
    """
    # File type one-hot (106)
    file_type_vec = _one_hot(
        props.get("file_extension", ""), vocabs.file_type, config.FILE_TYPE_VOCAB_SIZE
    )

    # HTTP status one-hot (68)
    status_str = str(props.get("http_status", "")) if props.get("http_status") else ""
    http_status_vec = _one_hot(
        status_str, vocabs.http_status, config.HTTP_STATUS_VOCAB_SIZE
    )

    # Content-Type one-hot (12)
    content_type_vec = _one_hot(
        props.get("content_type", ""), vocabs.content_type, config.ENCODING_VOCAB_SIZE
    )

    # Server one-hot (944)
    server_vec = _one_hot(
        props.get("server", ""), vocabs.server, config.SERVER_VOCAB_SIZE
    )

    # Lexical features (4): length, digit_count, special_char_count, path_depth
    lexical = np.array([
        props.get("length", 0),
        props.get("digit_count", 0),
        props.get("special_char_count", 0),
        props.get("path_depth", 0),
    ], dtype=np.float32)

    # Scalar features (4): entropy, has_query, has_fragment, head_failed
    scalars = np.array([
        props.get("entropy", 0.0),
        1.0 if props.get("has_query", False) else 0.0,
        1.0 if props.get("has_fragment", False) else 0.0,
        1.0 if props.get("head_failed", True) else 0.0,
    ], dtype=np.float32)

    # Temporal features (2): lifespan_days, recency_days
    temporal = np.array([
        props.get("lifespan_days", 0.0),
        props.get("recency_days", 0.0),
    ], dtype=np.float32)

    # Concatenate known features
    known = np.concatenate([
        file_type_vec, http_status_vec, content_type_vec,
        server_vec, lexical, scalars, temporal
    ])

    # Pad to target dimension
    target_dim = config.URL_FEATURE_DIM
    if known.shape[0] < target_dim:
        padding = np.zeros(target_dim - known.shape[0], dtype=np.float32)
        vec = np.concatenate([known, padding])
    else:
        vec = known[:target_dim]

    return vec
