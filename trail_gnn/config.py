import os

# Neo4j connection
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "trailpassword")
NEO4J_HTTP_URL = os.environ.get("NEO4J_HTTP_URL", "http://localhost:7474")

# APT groups — top 11 by event count in our Neo4j graph
# Training ignores events whose `apt` property is not in this list.
APT_GROUPS = [
    "Kimsuky", "Cobalt Group", "Lazarus Group", "APT28",
    "Mustang Panda", "Turla", "APT41", "Sandworm",
    "APT37", "APT29", "Gamaredon",
]
NUM_CLASSES = len(APT_GROUPS)
APT_TO_IDX = {apt: i for i, apt in enumerate(APT_GROUPS)}
IDX_TO_APT = {i: apt for apt, i in APT_TO_IDX.items()}

# Hierarchical attribution — nation-state mappings
# Adapted from Palo Alto Unit 42 tiered attribution framework.
#
# NOTE on Cobalt Group: financially-motivated cybercrime group with no
# authoritative nation-state attribution (operators are Russian-speaking
# but the group operates criminally, not as a state proxy). We mark it
# with None here rather than conflating "Cybercrime" with a nation.
# Tier-2 evaluation should exclude events whose true APT maps to None —
# see trail_gnn/training_hierarchical.py.
APT_TO_NATION = {
    "Kimsuky":       "North Korea",
    "Lazarus Group": "North Korea",
    "APT37":         "North Korea",
    "APT28":         "Russia",
    "APT29":         "Russia",
    "Turla":         "Russia",
    "Sandworm":      "Russia",
    "Gamaredon":     "Russia",
    "Mustang Panda": "China",
    "APT41":         "China",
    "Cobalt Group":  None,   # cybercrime, not nation-attributed
}

# Reverse mapping: nation-state → list of APT groups (None nations excluded)
NATION_TO_APTS = {}
for _apt, _nation in APT_TO_NATION.items():
    if _nation is not None:
        NATION_TO_APTS.setdefault(_nation, []).append(_apt)

# Nation-state class indices (for tier-1 classification)
NATIONS = sorted(n for n in set(APT_TO_NATION.values()) if n is not None)
NATION_TO_IDX = {n: i for i, n in enumerate(NATIONS)}
IDX_TO_NATION = {i: n for n, i in NATION_TO_IDX.items()}
NUM_NATIONS = len(NATIONS)

# APT indices that have no nation attribution (excluded from tier-2 metrics)
NON_NATION_APT_IDX = {
    i for apt, i in APT_TO_IDX.items() if APT_TO_NATION[apt] is None
}


def set_apt_groups(apts: list[str]) -> None:
    """
    Replace the active APT label set at runtime and rebuild every derived
    global that depends on it. Used by train_gnn_hierarchical.py when the
    user passes --apts to train on a custom subset (e.g. only the 6 APTs
    with ≥ 60 events, or only nation-state actors).

    Downstream modules import APT_GROUPS / APT_TO_IDX / NUM_CLASSES / NATIONS
    at call time, so as long as this runs before train_pipeline() starts,
    the override propagates cleanly. APT_TO_NATION is treated as a fixed
    reference table — we never mutate it, we just filter which APTs are
    in scope.
    """
    global APT_GROUPS, NUM_CLASSES, APT_TO_IDX, IDX_TO_APT
    global NATIONS, NATION_TO_IDX, IDX_TO_NATION, NUM_NATIONS
    global NATION_TO_APTS, NON_NATION_APT_IDX

    unknown = [a for a in apts if a not in APT_TO_NATION]
    if unknown:
        raise ValueError(
            f"Unknown APT(s) not in APT_TO_NATION table: {unknown}. "
            f"Add them to config.APT_TO_NATION first."
        )

    APT_GROUPS = list(apts)
    NUM_CLASSES = len(APT_GROUPS)
    APT_TO_IDX = {apt: i for i, apt in enumerate(APT_GROUPS)}
    IDX_TO_APT = {i: apt for apt, i in APT_TO_IDX.items()}

    NATION_TO_APTS = {}
    for apt in APT_GROUPS:
        n = APT_TO_NATION[apt]
        if n is not None:
            NATION_TO_APTS.setdefault(n, []).append(apt)

    NATIONS = sorted(NATION_TO_APTS.keys())
    NATION_TO_IDX = {n: i for i, n in enumerate(NATIONS)}
    IDX_TO_NATION = {i: n for n, i in NATION_TO_IDX.items()}
    NUM_NATIONS = len(NATIONS)

    NON_NATION_APT_IDX = {
        i for apt, i in APT_TO_IDX.items() if APT_TO_NATION[apt] is None
    }

# Tiered confidence thresholds (for determining recommended tier at inference)
# These are NOT graph-construction thresholds — v4 uses Dempster-Shafer Theory
# to compute continuous belief scores stored on Event nodes.
TIER3_CONFIDENCE = 0.45       # above this → recommend named actor
TIER2_CONFIDENCE = 0.30       # above this → recommend nation-state
# below TIER2_CONFIDENCE → recommend activity cluster only

# Feature dimensions (from TRAIL paper Section IV-B)
DOMAIN_FEATURE_DIM = 117   # 100 TLD + 9 DNS record counts + 1 NXDOMAIN + 4 lexical + 1 active_period + 2 temporal
IP_FEATURE_DIM = 509        # 249 country codes + 258 IP issuers + 2 temporal
URL_FEATURE_DIM = 1517      # 106+21+68+12+944+50+183+100+10+23 (temporal absorbed into padding)
# ASN nodes are structural only (paper §IV-C): features are zero placeholders
# at the GNN encoding dim so to_hetero propagation sees a compatible shape.
ASN_FEATURE_DIM = 64

# Vocabulary sizes (for one-hot encoding)
TLD_VOCAB_SIZE = 100        # top 99 + "other"
COUNTRY_VOCAB_SIZE = 249    # ISO 3166-1 alpha-2
ISSUER_VOCAB_SIZE = 258     # top 257 ASN descriptions + "other"
SERVER_VOCAB_SIZE = 944     # top 943 Server header values + "other"
FILE_TYPE_VOCAB_SIZE = 106  # top 105 file extensions + "other"
FILE_CLASS_VOCAB_SIZE = 21
HTTP_STATUS_VOCAB_SIZE = 68
ENCODING_VOCAB_SIZE = 12
OS_VOCAB_SIZE = 50
SERVICES_VOCAB_SIZE = 183

# Autoencoder hyperparameters (from TRAIL paper Section VI-C)
AE_HIDDEN_DIM = 512
AE_ENCODING_DIM = 64
AE_EPOCHS = 100
AE_LR = 0.001
AE_BATCH_SIZE = 256

# GraphSAGE hyperparameters (from TRAIL paper Section VI-C)
GNN_LAYERS = 4
GNN_HIDDEN_DIM = 512
GNN_ENCODING_DIM = 64       # input dim (autoencoder output)
GNN_OUTPUT_DIM = NUM_CLASSES
GNN_LR = 0.0001
GNN_EPOCHS = 200
GNN_AGGREGATION = "mean"

# Label Propagation (from TRAIL paper Section VI-B)
LP_ITERATIONS = 4

# Training
K_FOLDS = 5

# Model persistence
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

# Enrichment settings
HTTP_HEAD_TIMEOUT = 5       # seconds for URL HTTP HEAD requests
DNS_TIMEOUT = 3.0           # seconds for DNS queries
