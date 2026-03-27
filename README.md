# TRAIL — Tiered Reasoning for APT Intelligence Labeling

A GNN-based Advanced Persistent Threat (APT) attribution system that combines GraphSAGE message-passing with Label Propagation over a heterogeneous knowledge graph. Given an unknown IOC (domain, IP, or URL), the system attributes it to a specific threat actor with hierarchical confidence scoring based on Palo Alto Unit 42's tiered attribution framework.

Built as a Master's Capstone project at Simon Fraser University.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Phase 1: Graph Construction                    │
│  n8n Workflow (v5) → OTX API → Enrichment → Neo4j Knowledge Graph│
│  + Independent DST confidence scoring per pulse                   │
└──────────────────────┬───────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Phase 2: Training                              │
│  Neo4j → PyG HeteroData → Autoencoders (64-dim) → 4-Layer       │
│  GraphSAGE + SMOTE + DST-weighted loss → 5-fold CV               │
└──────────────────────┬───────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Phase 3: Attribution                           │
│  Unknown IOC → Enrich → GNN inference + Label Propagation →      │
│  60/40 Ensemble → Tiered Attribution (Named Actor / Nation /     │
│  Activity Cluster)                                                │
└──────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
MASTER_CAPSTONE/
├── trail_gnn/                        # Core Python package
│   ├── main.py                       # FastAPI service (all endpoints)
│   ├── config.py                     # Configuration & hyperparameters
│   ├── schemas.py                    # Pydantic request/response models
│   ├── model.py                      # 4-layer Heterogeneous GraphSAGE
│   ├── autoencoders.py               # IOC dimensionality reduction (→ 64-dim)
│   ├── training.py                   # Full training pipeline (SMOTE + k-fold CV)
│   ├── inference.py                  # GNN + LP ensemble prediction
│   ├── label_propagation.py          # Label propagation algorithm
│   ├── enrichment.py                 # Domain/IP/URL enrichment (DNS, ASN, lexical)
│   ├── feature_extraction.py         # Raw feature vector construction
│   ├── graph_export.py               # Neo4j → PyTorch Geometric export
│   ├── vocabularies.py               # One-hot encoding vocabularies
│   ├── neo4j_client.py               # Neo4j driver wrapper
│   └── models/                       # Trained model artifacts
│       ├── gnn_model.pt              # 4-layer GraphSAGE weights
│       ├── ae_domain.pt              # Domain autoencoder
│       ├── ae_ip.pt                  # IP autoencoder
│       ├── ae_url.pt                 # URL autoencoder
│       └── vocabularies.json         # Persisted vocabularies
│
├── trail/                            # Cloned TRAIL paper repository (King et al.)
│   ├── TKG_data/                     # Original dataset (2.1M nodes, 7.9M edges)
│   ├── model_weights/                # Pre-trained XGB/DNN/GNN from paper
│   ├── src/                          # Original TRAIL source code
│   └── load_tkg_to_neo4j.py          # Loader for paper's dataset
│
├── recalc_dst.py                     # Standalone DST recalculation script
│
├── TRAIL_Phase1_GraphConstruction_v5.json   # n8n workflow (Independent DST)
├── TRAIL_Phase1_GraphConstruction_v4.json   # n8n workflow (accumulated DST)
├── TRAIL_Phase2_Attribution.json            # n8n attribution workflow
└── README.md
```

## Knowledge Graph Schema (Neo4j)

### Node Types

| Node | Key Property | DST Fields | Temporal Fields |
|------|-------------|------------|-----------------|
| **Event** | `id` (OTX pulse ID) | `label_confidence`, `belief_named_actor`, `belief_nation_state`, `uncertainty`, `tag_exclusivity`, `evidence_weight`, `nation_coherence` | `pulse_created`, `pulse_modified` |
| **Domain** | `value` | — | `first_seen`, `last_seen` (derived) |
| **IP** | `value` | — | `first_seen`, `last_seen` (derived) |
| **URL** | `value` | — | — |
| **ASN** | `number` | — | — |

### Edge Types

| Edge | From → To | Properties |
|------|-----------|------------|
| **InReport** | Event → Domain/IP/URL | `indicator_created` |
| **ResolvesTo** | Domain → IP | `first_seen`, `last_seen` |
| **HostedOn** | URL → Domain | — |
| **InGroup** | Event → (APT grouping) | — |

## Dempster-Shafer Theory (DST) — Label Confidence

Each OTX pulse gets an independent confidence score measuring how trustworthy its APT label is. This is NOT accumulated across pulses — each Event node has its own score.

### Why DST?

- **No prior required** — unlike Bayesian inference which requires a prior distribution (where would that come from for threat attribution?), DST starts from evidence alone
- **Explicit uncertainty** — can assign belief to "I don't know" instead of distributing forced probabilities across known outcomes
- **Hierarchical compatibility** — belief in a named actor naturally subsumes belief in its nation-state
- **Established in cybersecurity** — Tian et al. (2020) combined deep learning with DST for insider threat detection; we extend this to threat attribution

### Three Data-Derived Signals

| Signal | Formula | Measures |
|--------|---------|----------|
| **Tag Exclusivity** | `(target_aliases / total_apt_aliases)²` if APT alias tags exist; `1/(1+N)` if none, where N = distinct APTs mentioned in pulse text | How exclusively this pulse references the target APT |
| **Evidence Weight** | `min(1.0, log₂(1+ioc_count) / log₂(51))` | How substantial the report is (log-normalized, capped at OTX page size of 50) |
| **Nation Coherence** | `1.0` match / `0.5` absent / `0.0` contradicts | Geographic tagging alignment with APT's known nation |

Rationale for each value:
- **Tag Exclusivity squared**: Penalizes ambiguity quadratically — a pulse tagging 2 APTs equally (0.5) scores 0.25, not 0.5
- **Evidence Weight log-normalized**: Diminishing returns — going from 1 to 10 IOCs matters more than 40 to 50
- **Nation Coherence 0.5 for absent**: DST maximum ignorance principle — no evidence for or against

### Mass Function (Per Pulse)

```
m_named  = tag_exclusivity × evidence_weight × nation_coherence
m_nation = (1 - tag_exclusivity) × evidence_weight × nation_coherence × 0.5
```

`m_named` requires all three signals to be strong. If any is zero, confidence collapses.

`m_nation` captures the leftover tag evidence that couldn't be assigned to a specific APT but still points to the nation/region. The `× 0.5` reflects that ambiguous tag evidence doesn't fully transfer to nation-level confidence — some of it is genuinely uncertain.

### Hierarchical Tier Beliefs

Since Named Actor ⊂ Nation-State ⊂ Activity Cluster:

| Tier | Field | Calculation | Meaning |
|------|-------|-------------|---------|
| Tier 3 — Named Actor | `belief_named_actor` | `m_named` | Confidence in the specific APT label |
| Tier 2 — Nation-State | `belief_nation_state` | `m_named + m_nation` | Always ≥ named (knowing APT28 implies knowing Russia) |
| Tier 1 — Activity Cluster | `activity_cluster` | Lookup: known state sponsor → "State-Sponsored", no known sponsor → "Cybercrime" | Label, not a score |
| — | `uncertainty` | `1 - m_named - m_nation` | Remaining unassigned belief mass |

### How the GNN Uses DST

- **`label_confidence`** → sample weight during training (high-confidence events contribute more to loss function)
- **Belief fields** → node features (GNN learns which events are reliable vs noisy)
- **Final attribution confidence** comes from GNN+LP output at inference time — DST only measures training data quality

## Timing Information

Five timestamps are collected throughout the pipeline:

| Timestamp | Location | What It Tells Us |
|-----------|----------|------------------|
| `pulse_created` | Event node | When the threat report was published |
| `pulse_modified` | Event node | When the report was last updated |
| `indicator_created` | InReport edge | When the IOC was first reported in this pulse |
| `first_seen` | ResolvesTo edge | When pDNS first observed this domain→IP resolution |
| `last_seen` | ResolvesTo edge | When pDNS last observed this resolution |

### Temporal Features in the GNN

Derived from timestamps and added to IOC feature vectors:

- **`lifespan_days`** = `last_seen - first_seen` — infrastructure persistence
  - Short lifespan (hours/days) → disposable C2, sophisticated APT rotating infrastructure
  - Long lifespan (years) → legitimate service or persistent implant
- **`recency_days`** = `now - last_seen` — how stale the infrastructure is
  - Recent → active campaign, IOC still attributable
  - Stale → infrastructure may have changed hands, weaker attribution

These are embedded into feature vectors (Domain 117-dim, IP 509-dim, URL 1517-dim), compressed through autoencoders to 64-dim, and learned by GraphSAGE during message passing. The GNN discovers patterns like "APT28 uses short-lived domains on Russian ASNs" vs "Kimsuky uses persistent infrastructure on Korean hosting."

## Model Architecture

### Autoencoder (Dimensionality Reduction)

Each IOC type has its own autoencoder that compresses high-dimensional features to a uniform 64-dim encoding:

```
Domain:  117-dim → Linear(512) → ReLU → Linear(64)  → 64-dim
IP:      509-dim → Linear(512) → ReLU → Linear(64)  → 64-dim
URL:    1517-dim → Linear(512) → ReLU → Linear(64)  → 64-dim
```

Trained with MSE reconstruction loss. The autoencoder learns which features (including temporal) are discriminative.

### GraphSAGE (4-Layer Heterogeneous GNN)

```
Input: 64-dim node embeddings (all types unified)
  → SAGEConv Layer 1 (64 → 512, mean aggregation) + LayerNorm + ReLU
  → SAGEConv Layer 2 (512 → 512) + LayerNorm + ReLU
  → SAGEConv Layer 3 (512 → 512) + LayerNorm + ReLU
  → SAGEConv Layer 4 (512 → 10) + L2 Norm
  → Softmax → probability distribution over 10 APT classes
```

Each layer aggregates neighbor features via mean pooling. After 4 layers, each node encodes its entire 4-hop neighborhood — meaning an Event node carries information from its IOCs, their shared IPs, those IPs' other domains, and so on.

Training uses:
- **SMOTE** for class balancing (synthetic events inherit class mean `label_confidence`)
- **DST-weighted cross-entropy loss** (high-confidence events matter more)
- **5-fold stratified cross-validation**

### Label Propagation

Independent from the GNN — uses only graph structure:

1. Build Event-Event adjacency (two events are connected if they share ≥1 IOC)
2. Symmetric normalization: D^(-1/2) × A × D^(-1/2)
3. 4 iterations: spread labels, re-clamp known labels each step
4. Return softmax probabilities

### Ensemble

```
final = 0.6 × GNN_output + 0.4 × LP_output
```

GNN captures **feature patterns** (what the IOC looks like + temporal behavior). LP captures **structural patterns** (what it's connected to). Combined is stronger than either alone.

## Tiered Attribution (Unit 42 Framework)

| Tier | Level | Example | Confidence Source |
|------|-------|---------|-------------------|
| Tier 3 | Named Actor | "APT28" | GNN+LP ensemble score for top APT class |
| Tier 2 | Nation-State | "Russia" | Sum of scores for all APTs from that nation |
| Tier 1 | Activity Cluster | "State-Sponsored" | Lookup: known state sponsor → "State-Sponsored", else → "Cybercrime" |

Recommendation thresholds (applied at inference):
- Tier 3 confidence ≥ 0.45 → recommend named actor
- Tier 2 confidence ≥ 0.30 → recommend nation-state
- Below 0.30 → activity cluster only

## Setup

### Prerequisites

- Python 3.12+
- Neo4j Desktop (or Neo4j 5.x server)
- Docker (for n8n)
- OTX AlienVault API key

### 1. Install Python Dependencies

```bash
cd MASTER_CAPSTONE
pip install torch torch-geometric fastapi uvicorn neo4j requests tldextract ipwhois scikit-learn imbalanced-learn
```

### 2. Start Neo4j

Create a new Neo4j Desktop instance:
- Name: `trail2`
- Password: `trailpassword`
- Start the instance (runs on bolt://localhost:7687, HTTP on :7474)

### 3. Start n8n (Docker)

```bash
docker start n8n
# Access at http://localhost:5678
```

### 4. Import n8n Workflow

```bash
docker cp TRAIL_Phase1_GraphConstruction_v5.json n8n:/tmp/v5.json
docker exec n8n n8n import:workflow --input=/tmp/v5.json
```

Open http://localhost:5678, attach OTX API credentials to the HTTP Request nodes, and execute.

### 5. Start FastAPI Service

```bash
cd MASTER_CAPSTONE
python3 -m uvicorn trail_gnn.main:app --host 0.0.0.0 --port 8001
```

## How to Run

### Graph Construction (Phase 1)

**Option A: n8n workflow**
1. Open http://localhost:5678
2. Open "TRAIL Phase 1 - Graph Construction v5 (Independent DST)"
3. Click "Execute workflow"
4. Workflow skips already-loaded APTs on restart

**Option B: Recalculate DST on existing data**
```bash
OTX_API_KEY=your_key python3 recalc_dst.py
```

### Training (Phase 2)

```bash
curl -X POST http://localhost:8001/train \
  -H "Content-Type: application/json" \
  -d '{"k_folds": 5, "ae_epochs": 100, "gnn_epochs": 200}'
```

### Attribution Query (Phase 3)

```bash
curl -X POST http://localhost:8001/attribute \
  -H "Content-Type: application/json" \
  -d '{"iocs": [{"type": "domain", "value": "suspicious.example.com"}]}'
```

Example response:
```json
{
  "iocs_processed": 1,
  "tiered": {
    "tier3_named_actor": {"prediction": "APT28", "confidence": 0.82, "assessment": "high_confidence"},
    "tier2_nation_state": {"prediction": "Russia", "confidence": 0.91, "assessment": "high_confidence"},
    "tier1_activity_cluster": {"prediction": "State-Sponsored", "confidence": 0.91, "assessment": "high_confidence"},
    "recommended_tier": 3,
    "summary": "High-confidence attribution to APT28 (Russia, State-Sponsored)"
  }
}
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | Health check, Neo4j connectivity, model state, graph stats |
| `/enrich/domain` | POST | DNS + lexical + ASN enrichment |
| `/enrich/ip` | POST | Country + ASN enrichment |
| `/enrich/url` | POST | Lexical + HTTP HEAD enrichment |
| `/train` | POST | Async training (5-fold CV + SMOTE + DST weighting) |
| `/predict` | POST | GNN + LP ensemble prediction on labeled graph |
| `/label-propagation` | POST | LP-only predictions |
| `/attribute` | POST | Ad-hoc IOC attribution (enrich → insert → predict → cleanup) |
| `/store-results` | POST | Save predictions to Neo4j |
| `/results` | GET | Query stored predictions |

## How to Test

### Service health
```bash
curl http://localhost:8001/status
```

### Neo4j graph stats
```bash
curl -s -u neo4j:trailpassword http://localhost:7474/db/neo4j/tx/commit \
  -H "Content-Type: application/json" \
  -d '{"statements":[
    {"statement":"MATCH (e:Event) RETURN e.apt AS apt, count(e) AS pulses ORDER BY pulses DESC"},
    {"statement":"MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC"},
    {"statement":"MATCH ()-[r]->() RETURN count(r) AS total_rels"}
  ]}'
```

### Verify DST scores
```cypher
MATCH (e:Event)
RETURN e.apt, e.name, e.label_confidence, e.belief_nation_state,
       e.tag_exclusivity, e.evidence_weight, e.nation_coherence, e.uncertainty
ORDER BY e.apt, e.label_confidence DESC
```

### Test enrichment
```bash
curl -X POST http://localhost:8001/enrich/domain \
  -H "Content-Type: application/json" -d '{"domain": "example.com"}'
```

### Test attribution
```bash
curl -X POST http://localhost:8001/attribute \
  -H "Content-Type: application/json" \
  -d '{"iocs": [
    {"type": "domain", "value": "evil.ru"},
    {"type": "ip", "value": "1.2.3.4"},
    {"type": "url", "value": "http://malware.example.com/payload.exe"}
  ]}'
```

### Run predictions on labeled events
```bash
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{"include_labeled": true}'
```

## Configuration

All hyperparameters are in `trail_gnn/config.py`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| GNN_LAYERS | 4 | GraphSAGE depth |
| GNN_HIDDEN_DIM | 512 | Hidden layer width |
| AE_ENCODING_DIM | 64 | Compressed feature dimension |
| GNN_LR | 0.0001 | Learning rate |
| GNN_EPOCHS | 200 | Training epochs per fold |
| K_FOLDS | 5 | Cross-validation folds |
| LP_ITERATIONS | 4 | Label propagation steps |
| TIER3_CONFIDENCE | 0.45 | Named actor recommendation threshold |
| TIER2_CONFIDENCE | 0.30 | Nation-state recommendation threshold |

## APT Groups Tracked

| APT | Nation | Activity Cluster |
|-----|--------|-----------------|
| APT28 (Fancy Bear) | Russia | State-Sponsored |
| APT29 (Cozy Bear) | Russia | State-Sponsored |
| Turla | Russia | State-Sponsored |
| APT37 (Reaper) | North Korea | State-Sponsored |
| APT38 (Lazarus) | North Korea | State-Sponsored |
| Kimsuky | North Korea | State-Sponsored |
| APT27 (TG-3390) | China | State-Sponsored |
| Mustang Panda | China | State-Sponsored |
| OceanLotus (APT32) | Vietnam | State-Sponsored |
| FIN11 | — | Cybercrime |

## References

- King et al., "TRAIL: A Tiered Reasoning Framework for Attribution and Intelligence Labeling," IEEE ICDE 2025
- Tian et al., "Deep Learning and Dempster-Shafer Theory Based Insider Threat Detection," 2020
- Palo Alto Unit 42, "Threat Attribution: A Critical Component of Threat Intelligence"
- Hamilton et al., "Inductive Representation Learning on Large Graphs" (GraphSAGE), NeurIPS 2017
