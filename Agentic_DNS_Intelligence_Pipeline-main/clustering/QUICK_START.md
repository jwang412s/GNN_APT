# Quick Start Guide - Phase 2

## Installation and First Run (5 minutes)

### Prerequisites

```bash
python --version  # Requires 3.8+
pip list | grep -E "(scikit-learn|hdbscan|numpy|pandas)"
```

### Basic Usage

```bash
# Use default configuration (practical preset)
python domain_clustering/main.py enriched_domains_hq.csv

# Output will be generated to clustering_output/
ls clustering_output/
```

### Key Output Files

| File | Description |
|------|-------------|
| clustering_results.csv | Cluster assignment for each domain |
| campaign_patterns.csv | Cluster patterns for each incident |
| incidents_detailed.json | Details of 67 infrastructure incidents |
| clustering_summary.json | Statistical summary |
| clustering_pca.png | PCA visualization |
| clustering_heatmap.png | Distance matrix heatmap |

## Phase 2 Key Changes

1. **Architecture**: Single file → 19 modules

2. **Quality**: Silhouette → Dupont Structural Quality

3. **Incident Grouping**: Event-based → Infrastructure-based (67 incidents)

4. **Weights**: Updated to `[1.2, 1.0, 0.3, 2.0, 1.8]`

## Frequently Asked Questions

**Q: Why are there 67 incidents instead of 58?**

A: Infrastructure-based grouping discovered 67 unique (registrar_id, asn) combinations

**Q: How to adjust weights?**

A: Edit the CONFIG dictionary in domain_clustering/config/settings.py

**Q: My results differ from Phase 1?**

A: Expected. Structural Quality and infrastructure grouping are Phase 2 changes

**Q: How to use LLM integration (Phase 3)?**

A: Currently unavailable. Framework is in place, awaiting Phase 3 implementation

## Running Tests

```bash
bash run_all_tests.sh
```

Expected: All 6 tests pass ✅

## Documentation

- Full architecture: domain_clustering/ARCHITECTURE.md

- Module diagram: ARCHITECTURE_DIAGRAM.md

- Completion report: PHASE2_COMPLETION_REPORT.md
