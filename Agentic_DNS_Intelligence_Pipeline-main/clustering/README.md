# Clustering Module

This directory is reserved for the future clustering integration.

The current version of the project does not include clustering inside the automation pipeline. 
Once the implementation is finished, the integration process will begin.

> Scope: module `domain_clustering`. **Important: the n8n workflow currently does NOT include clustering code; outputs here are preliminary. Future n8n interfaces and automation are planned but not yet integrated.**

## Method & Sources
- Clustering strategy and distance weights follow the paper definitions (DBSCAN/HDBSCAN dual-layer design) [Leite 2024, Table 1, p.7].
- Structural quality filtering uses the Dupont feature-average dissimilarity thresholds (T_DISS=0.2, T_GOOD=3) to retain high-quality clusters [Structure_quality_score_Similarity-Based_Clustering_For_IoT_Device_Classification].

## Module Layout (concise)
- Entry: `main.py` (CLI), `__init__.py` (programmatic `run_pipeline`)
- Config: `config/settings.py` (weights, thresholds, time window, toggles)
- Metrics: `metrics/` (Levenshtein, Jaccard, registrar, ASN; aggregation of Equation 1)
- Clustering: `clustering/` (`cluster_hdbscan`, `cluster_dbscan`, `cluster_combined`)
- Quality: `quality/` (Dupont structural quality, quality filter)
- Incident: `incident/` (infrastructure grouping by registrar_id + asn)
- Pipeline: `pipeline/clustering_pipeline.py` (steps 1-8 orchestration)

See `domain_clustering/ARCHITECTURE.md` for full details.

## Requirements
- Python ≥ 3.8 (recommended 3.10+)
- Dependencies: see root `requirements.txt` (includes hdbscan, scikit-learn, pandas, etc.)
- Input: enriched CSV/Parquet, e.g., `enriched_domains_hq.csv`

## Quickstart (aligned with `QUICK_START.md`)
```bash
# Basic run (CLI entry is main.py)
python domain_clustering/main.py enriched_domains_hq.csv

# Default preset = practical (HDBSCAN-only unless you set dbscan_enabled=True)
# Outputs will appear in clustering_output/
ls clustering_output/

# Optional: custom window (days)
python domain_clustering/main.py enriched_domains_hq.csv --window 200

# Optional: provide labeled data for evaluation
python domain_clustering/main.py enriched_domains_hq.csv --labeled labeled.csv
```

## Key Design Points
- **HDBSCAN-only default**: `dbscan_enabled=False` in `config/settings.py`; only HDBSCAN runs with structural-quality filtering. Enable DBSCAN by setting it to True. Combine methods also available(DBSCAN first - high completeness then HDBSCAN - wide scan; but weight needs to be adjusted more based on the completeness of the enriched dataset).
- **Structural quality filter**: Dupont feature-average dissimilarity with `T_DISS=0.2` and `T_GOOD=3` in `quality/structural_quality.py`.
- **Infrastructure grouping**: incident_id derived from `(registrar_id, asn)` in `incident/incident_grouping.py`.

## Outputs
- Results and visualizations are written to `clustering_output/` by default (per-domain clustering results, campaign patterns, PCA/heatmap, quality summary) [PIPELINE_GUIDE §clustering_output].

## References
- Leite et al. 2024. *Using DNS Patterns for Automated Cyber Threat Attribution*. ACM ARES. `archive/historical_docs/clustering_Using_DNS_Patterns_for_Automated_Cyber_Threat_Attribution.pdf`
- Dupont et al. 2021. *Similarity-Based Clustering For IoT Device Classification*. `archive/historical_docs/Structure_quality_score_Similarity-Based_Clustering_For_IoT_Device_Classification.pdf`
