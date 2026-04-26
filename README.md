# TRAIL — Tiered Reasoning for APT Intelligence Labeling

A GraphSAGE-based pipeline for attributing network indicators of compromise
(domains, IPs, URLs) to one of a fixed set of named APT groups, with a
Dempster–Shafer confidence hierarchy that lets the model commit to a
named actor, a nation state, or a coarse activity cluster depending on
how concentrated the softmax is.

Built on top of the TRAIL paper (King et al., ICDE 2025) as a Master's
Capstone project at Simon Fraser University.

---

## Folder Structure

```
MASTER_CAPSTONE/
├── archive/old_pipeline/
│   └── collect_otx.py              # AlienVault OTX collector → Neo4j
│
├── trail_gnn/                      # Core Python package
│   ├── neo4j_client.py             # Neo4j driver wrapper
│   ├── graph_export.py             # Neo4j → PyG graph export
│   ├── feature_extraction.py       # Per-IOC feature vectors
│   ├── autoencoders.py             # Per-type IOC autoencoders (→ 64-dim)
│   ├── model.py                    # Heterogeneous GraphSAGE classifier
│   ├── training.py                 # Flat training loop
│   ├── training_hierarchical.py    # Tiered (DST) training loop
│   ├── otx_enrichment.py           # OTX API wrappers (pDNS, ASN)
│   └── models/                     # Trained checkpoints land here
│
├── train_gnn_hierarchical.py       # Train the GNN (entry point)
├── train_gnn_temporal_split.py     # Forward/backward temporal-split runs
├── predict_paper_server.py         # FastAPI server (/attribute endpoint)
│
├── trail/                          # Cloned TRAIL paper repo (reference)
├── sandbox/year_drop/              # Year-drop ablation experiment
└── papers/                         # Reference PDFs
```

The three things you actually run from a clean checkout are:

1. `archive/old_pipeline/collect_otx.py` — pulls events from OTX into Neo4j.
2. `train_gnn_hierarchical.py` — trains the GNN on the Neo4j graph.
3. `predict_paper_server.py` — serves single-IOC attribution over HTTP.

---

## Prerequisites

- Python 3.12+
- Neo4j 5.x (Desktop or server) reachable on `bolt://localhost:7687`
- An AlienVault OTX API key (one or more)

Install Python dependencies:

```bash
cd MASTER_CAPSTONE
pip install -r trail_gnn/requirements.txt
```

Set Neo4j credentials (defaults shown):

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="trailpassword"
```

---

## 1. Collect Data from AlienVault OTX

The collector pulls pulses for each APT in `trail_gnn/config.py:APT_GROUPS`,
filters out ambiguously-labelled and near-duplicate pulses, enriches IOCs
with passive DNS and ASN lookups, and writes everything to Neo4j.

Set one or more OTX API keys (multiple keys are rotated on rate limits):

```bash
export OTX_API_KEYS="key1,key2,key3"          # preferred
# or for a single key:
export OTX_API_KEY="your_single_key"
```

Run a full collection across all configured APTs:

```bash
python3 archive/old_pipeline/collect_otx.py
```

Useful flags:

```bash
# Restrict to one APT
python3 archive/old_pipeline/collect_otx.py --apt APT28

# Restrict to a date window
python3 archive/old_pipeline/collect_otx.py \
    --since 2023-04-01 --until 2026-04-01

# Skip enrichment (pulses + indicators only, no pDNS / ASN)
python3 archive/old_pipeline/collect_otx.py --skip-enrichment
```

The collector is checkpointed: every processed pulse id and the in-memory
ASN / reverse-pDNS caches are flushed to `otx_checkpoint.json` after every
pulse. A re-run resumes from where the previous run left off. Delete the
checkpoint file to start over.

Logs land in `logs/otx_collector.log` (full trace) and
`logs/otx_skipped.log` (one line per dropped pulse with reason). Verify
the result in Neo4j:

```cypher
MATCH (e:Event)
RETURN e.apt AS apt, count(e) AS pulses
ORDER BY pulses DESC
```

---

## 2. Train the GNN

The training script reads the Neo4j graph populated in step 1, builds
per-type IOC feature autoencoders, and trains a 5-fold cross-validated
GraphSAGE classifier with hierarchical (Tier-3 named-actor /
Tier-2 nation) evaluation.

Basic run:

```bash
python3 -u train_gnn_hierarchical.py --name my_first_run
```

Useful flags:

```bash
# Restrict to a subset of APTs (recommended — long-tail classes do not learn)
python3 -u train_gnn_hierarchical.py \
    --name hier_7apt \
    --apts 'Kimsuky,APT28,Mustang Panda,Turla,APT37,APT29,APT41'

# Disable temporal recency weighting (treat every event as equally fresh)
python3 -u train_gnn_hierarchical.py --name no_temp --zero-temporal

# Adjust tier confidence thresholds
python3 -u train_gnn_hierarchical.py --name custom_thresh \
    --tier3-threshold 0.5 --tier2-threshold 0.25

# Override fold count or epoch budget
python3 -u train_gnn_hierarchical.py --name short_run \
    --folds 3 --ae-epochs 50 --gnn-epochs 100
```

Outputs land in `trail_gnn/models/<name>/`:

- `gnn_model.pt` — trained GraphSAGE checkpoint
- `ae_domain.pt`, `ae_ip.pt`, `ae_url.pt` — per-type autoencoders
- `vocabularies.json` — one-hot vocabularies fixed at training time
- `training_results.json` — per-fold accuracies and per-APT breakdown

Training time on the 2023–2026 corpus (951 labelled events, 7 APTs) is
roughly 4–5 hours on CPU.

---

## 3. Serve Single-IOC Attribution (Paper-Trained GNN)

`predict_paper_server.py` is a FastAPI service that loads the
TRAIL paper's pre-trained 2-layer GraphSAGE checkpoint along with the
paper's full TKG, and exposes two endpoints:

- `POST /predict_event` — predict on an event already in the graph
  (sanity check; no enrichment).
- `POST /attribute` — take one or more raw IOCs, enrich them, splice
  them into the graph as a temporary event, run inference, and return
  the tiered Dempster–Shafer prediction.

### Default Model

The server loads the paper's pre-trained 2-layer GraphSAGE checkpoint
from the cloned TRAIL repository — specifically the best-fold
checkpoint (validation balanced accuracy $0.777$):

```
trail/src/weights/2-layer/gnn_train-0.777_max_lprop+feats+ae-new-data.pt
```

The graph it serves predictions over is the paper's full TKG:

```
trail/TKG_data/otx_dataset/full_graph_csr.pt
```

Both paths are hardcoded near the top of `predict_paper_server.py`
(`WEIGHTS_PATH` and `GRAPH_PATH`). To serve a different checkpoint —
for example a model trained by `train_gnn_hierarchical.py` on the
2023–2026 corpus, or one of the year-drop ensemble checkpoints in
`sandbox/year_drop/{A,B,C,D}/weights/` — edit those two constants.

### Using Your Own Re-Trained Checkpoint

By default the server loads the paper authors' pre-trained checkpoint —
**not** anything trained by `train_gnn_hierarchical.py` in this repo.
To serve our re-trained TRAIL baseline (the year-drop config-A run,
which uses the full corpus with no events dropped), point `WEIGHTS_PATH`
at one of the 5 fold checkpoints:

```python
# predict_paper_server.py, near the top
WEIGHTS_PATH = os.path.join(
    "sandbox", "year_drop", "A", "weights", "fold0.pt",
)
```

`GRAPH_PATH` stays the same — config A was trained on the same paper
TKG (`trail/TKG_data/otx_dataset/full_graph_csr.pt`).

For a proper paper-comparable evaluation, ensemble all 5 folds by
averaging softmax outputs across `fold0.pt`–`fold4.pt`. See
`sandbox/year_drop/infer_neo4j.py` (`get_fold_paths` + the averaging
loop) for the reference pattern; porting it into the FastAPI handler
is a one-function change.

### Prerequisites

The default model requires the cloned TRAIL paper repository to be
present at `./trail/` with its `src/`, `TKG_data/otx_dataset/`, and
`src/weights/2-layer/` subdirectories populated. The TRAIL repo and
its dataset are not committed to this repository (they are large and
mirrored from the original authors); clone them in alongside this
repo before starting the server:

```bash
git clone https://github.com/HewlettPackard/TRAIL.git trail
# then download TKG.zip and the 2-layer weights as documented in
# the TRAIL repo README and unpack into trail/TKG_data/ and
# trail/src/weights/ respectively.
```

### Start

```bash
python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823
```

Wait for `[ready] server up.` on stdout, then check health:

```bash
curl http://localhost:47823/status
```

Attribute a single domain:

```bash
curl -X POST http://localhost:47823/attribute \
  -H "Content-Type: application/json" \
  -d '{"iocs": [{"type": "domain", "value": "suspicious.example.com"}]}'
```

Attribute a mixed batch:

```bash
curl -X POST http://localhost:47823/attribute \
  -H "Content-Type: application/json" \
  -d '{"iocs": [
    {"type": "domain", "value": "evil.ru"},
    {"type": "ip", "value": "1.2.3.4"},
    {"type": "url", "value": "http://malware.example.com/payload.exe"}
  ]}'
```

Example response:

```json
{
  "iocs_processed": 1,
  "predicted_apt": "APT28",
  "confidence": 0.82,
  "tiered": {
    "tier3_named_actor":      {"prediction": "APT28",  "confidence": 0.82, "assessment": "high_confidence"},
    "tier2_nation_state":     {"prediction": "Russia", "confidence": 0.91, "assessment": "high_confidence"},
    "tier1_activity_cluster": {"prediction": "State-sponsored (Russia)", "confidence": 0.91, "assessment": "high_confidence"},
    "recommended_tier": 3,
    "summary": "Tier-3 actor: APT28 (0.82); Tier-2 nation: Russia (0.91); Tier-1 cluster: State-sponsored (Russia). Recommended tier: 3."
  }
}
```

Each `/attribute` call grows the in-memory graph slightly; restart the
server periodically (or after a large batch) to reset.

---

## End-to-End in Three Commands

```bash
# 1. Collect (hours; checkpointed, safe to interrupt)
export OTX_API_KEYS="key1,key2"
python3 archive/old_pipeline/collect_otx.py

# 2. Train (a few hours on CPU)
python3 -u train_gnn_hierarchical.py \
    --name hier_7apt \
    --apts 'Kimsuky,APT28,Mustang Panda,Turla,APT37,APT29,APT41'

# 3. Serve attribution (uses the paper's pre-trained 2-layer GNN by
#    default — see Section 3 above to swap in your own checkpoint)
python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823
```

## Quickstart: Attribute an IOC with the Paper-Trained GNN

If you only want to query the pre-trained model from the TRAIL paper
without retraining anything:

```bash
# 1. Clone the TRAIL paper repo and its dataset/weights into ./trail
git clone https://github.com/HewlettPackard/TRAIL.git trail
# (then download TKG.zip + 2-layer weights as the TRAIL README describes)

# 2. Install dependencies
pip install -r trail_gnn/requirements.txt

# 3. Start the server
python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823

# 4. Attribute an IOC
curl -X POST http://localhost:47823/attribute \
  -H "Content-Type: application/json" \
  -d '{"iocs": [{"type": "domain", "value": "suspicious.example.com"}]}'
```

---

## References

- King et al., *TRAIL: A Knowledge Graph-based Approach for Attributing
  Advanced Persistent Threats*, IEEE ICDE 2025.
- Sentz & Ferson, *Combination of Evidence in Dempster–Shafer Theory*,
  Sandia Tech. Rep. SAND2002-0835, 2002.
- Palo Alto Unit 42, *Unit 42 Attribution Framework*, 2024.
