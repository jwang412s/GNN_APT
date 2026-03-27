import os

# Neo4j connection
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "trailpassword")
NEO4J_HTTP_URL = os.environ.get("NEO4J_HTTP_URL", "http://localhost:7474")

# APT groups (10 targets from TRAIL paper's top groups)
APT_GROUPS = [
    "APT28", "APT29", "APT38", "APT37", "Kimsuky",
    "APT27", "FIN11", "Mustang Panda", "OceanLotus", "Turla",
]
NUM_CLASSES = len(APT_GROUPS)
APT_TO_IDX = {apt: i for i, apt in enumerate(APT_GROUPS)}
IDX_TO_APT = {i: apt for apt, i in APT_TO_IDX.items()}

# Hierarchical attribution — nation-state mappings
# Adapted from Palo Alto Unit 42 tiered attribution framework
APT_TO_NATION = {
    "APT28":         "Russia",
    "APT29":         "Russia",
    "Turla":         "Russia",
    "APT37":         "North Korea",
    "APT38":         "North Korea",
    "Kimsuky":       "North Korea",
    "APT27":         "China",
    "Mustang Panda": "China",
    "OceanLotus":    "Vietnam",
    "FIN11":         "Cybercrime",
}

# Reverse mapping: nation-state → list of APT groups
NATION_TO_APTS = {}
for _apt, _nation in APT_TO_NATION.items():
    NATION_TO_APTS.setdefault(_nation, []).append(_apt)

# Nation-state class indices (for tier-1 classification)
NATIONS = sorted(set(APT_TO_NATION.values()))
NATION_TO_IDX = {n: i for i, n in enumerate(NATIONS)}
IDX_TO_NATION = {i: n for n, i in NATION_TO_IDX.items()}
NUM_NATIONS = len(NATIONS)

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
