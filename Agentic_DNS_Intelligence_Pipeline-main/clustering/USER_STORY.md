# User Story: Running the DNS Clustering Pipeline

This document walks through the complete user journey from setup to interpreting results.

## Prerequisites

### 1. Environment Setup

**System Requirements:**
- Python ≥ 3.8 (recommended 3.10+)
- Operating System: Linux, macOS, or Windows

**Install Dependencies:**
```bash
cd clustering
pip install -r requirements.txt
```

Key dependencies include:
- `hdbscan>=0.8.33` - Clustering algorithm
- `scikit-learn>=1.6.1` - DBSCAN clustering
- `pandas>=2.3.3` - Data processing
- `numpy>=2.0.2` - Numerical operations
- `python-Levenshtein>=0.21.0` - String distance metrics
- `tqdm>=4.65.0` - Progress bars

### 2. Prepare Your Data

**Input Format:** CSV or Parquet file with enriched domain data

**Required Columns:**
- `domain` (required) - Domain name (e.g., "example.com")
- `subdomains` (optional) - Semicolon-separated subdomains (e.g., "www;mail;ftp")
- `email_user` (optional) - Email username part (e.g., "admin")
- `registrar` (optional) - Registrar name (e.g., "Namecheap, Inc. (ID1068)")
- `registrar_id` (optional) - IANA registrar ID (e.g., "1068")
- `asn` (optional) - Autonomous System Number (e.g., "394354")
- `host_provider` (optional) - Host provider with ASN (e.g., "CIRA-CLOUD2, CA (AS394354)")
- `ts` (optional) - Timestamp (will be auto-generated if missing)
- `collection_date`, `first_seen`, `last_seen` (optional) - Alternative timestamp fields

**Example Input CSV:**
```csv
domain,subdomains,email_user,registrar,registrar_id,asn,host_provider,ts
malicious1.com,www;mail,admin,"Namecheap, Inc. (ID1068)",1068,394354,"CIRA-CLOUD2, CA (AS394354)",2024-01-15
malicious2.com,www,admin,"Namecheap, Inc. (ID1068)",1068,394354,"CIRA-CLOUD2, CA (AS394354)",2024-01-16
```

**Note:** If you have raw domains without enrichment, you'll need to enrich them first using the `feature_engineering/domain_enrichment.py` script.

---

## Step 1: Basic Run (Default Configuration)

**Command:**
```bash
python domain_clustering/main.py enriched_domains_hq.csv
```

**What Happens:**
1. **Data Loading** - Loads and validates your CSV/Parquet file
2. **Time Window Filtering** - Filters to last 150 days (default)
3. **Distance Matrix** - Computes pairwise distances (cached for future runs)
4. **Clustering** - Runs HDBSCAN-only clustering (default mode)
5. **Quality Filtering** - Removes low-quality clusters using structural quality
6. **Incident Grouping** - Groups clusters by infrastructure (registrar_id + ASN)
7. **Output Generation** - Creates results files and visualizations

**Default Configuration:**
- Preset: `practical` (weights: [1.2, 1.0, 0.3, 2.0, 1.8])
- Time window: 150 days
- Algorithm: HDBSCAN-only (`dbscan_enabled=False`)
- Quality filtering: Enabled (structural quality threshold: 0.20)

**Output Location:** `clustering_output/`

---

## Step 2: Customize Time Window

**Command:**
```bash
python domain_clustering/main.py enriched_domains_hq.csv --window 200
```

**What This Does:**
- Filters domains to the last 200 days instead of 150
- Useful for analyzing longer-term campaigns or historical data

**Use Cases:**
- `--window 30` - Recent threats only
- `--window 365` - Full year analysis
- `--window 0` - All data (no time filtering)

---

## Step 3: Choose Different Weight Presets

**Command:**
```bash
python domain_clustering/main.py enriched_domains_hq.csv --preset baseline
```

**Available Presets:**
- `baseline` - Equal weights [1.0, 1.0, 1.0, 1.0, 1.0]
  - All features equally important
  - Good for exploratory analysis
  
- `practical` (default) - [1.2, 1.0, 0.3, 2.0, 1.8]
  - Registrar and ASN weighted highest
  - Email weighted lowest
  - Recommended for most use cases
  
- `conservative` - [1.0, 1.2, 0.2, 1.2, 1.6]
  - More balanced, less aggressive
  - Good when data quality is uncertain

**What Presets Affect:**
- How distances are computed between domains
- Which features matter most for clustering
- Cluster boundaries and sizes

---

## Step 4: Enable Combined DBSCAN + HDBSCAN Mode

**To enable combined mode, edit `domain_clustering/config/settings.py`:**
```python
CONFIG["dbscan_enabled"] = True
```

**Then run:**
```bash
python domain_clustering/main.py enriched_domains_hq.csv
```

**What This Does:**
1. Runs DBSCAN first (high precision, strict filtering)
2. Runs HDBSCAN on full matrix (high recall, wider scan)
3. Combines results: DBSCAN clusters take precedence, HDBSCAN fills gaps

**When to Use:**
- When you want maximum coverage (both precision and recall)
- When you have high-quality enriched data
- When you need to catch both tight clusters and loose associations

---

## Step 5: Provide Labeled Data for Evaluation

**Command:**
```bash
python domain_clustering/main.py enriched_domains_hq.csv --labeled ground_truth.csv
```

**What This Does:**
- Runs the clustering pipeline
- Compares results against labeled ground truth
- Generates evaluation metrics (if evaluation module is fully implemented)

**Labeled Data Format:**
- Should have same structure as input data
- Include ground truth cluster/incident labels
- Used for validation and performance measurement

---

## Step 6: Interpret Results

### Output Files Overview

**1. `clustering_results.csv`**
- **Purpose:** Per-domain clustering results
- **Columns:**
  - All original columns from input
  - `cluster_id` - Assigned cluster ID (-1 = noise)
  - `cluster_quality` - Quality score [0, 1]
  - `source_algo` - Which algorithm found it ("DBSCAN" or "HDBSCAN")
  - `cluster_persistence` - HDBSCAN persistence score (if available)

**Example:**
```csv
domain,cluster_id,cluster_quality,source_algo,cluster_persistence
malicious1.com,0,0.8,HDBSCAN,0.75
malicious2.com,0,0.8,HDBSCAN,0.75
malicious3.com,1,0.6,HDBSCAN,0.50
noise1.com,-1,0.0,NOISE,NaN
```

**2. `campaign_patterns.csv`**
- **Purpose:** Incident-level cluster patterns
- **Columns:**
  - `incident_id` - Infrastructure-based incident ID
  - `pattern_set` - Semicolon-separated cluster IDs

**Example:**
```csv
incident_id,pattern_set
infra_1068|394354,0;1;2
infra_1250|55195,3;4
```

**3. `incidents_detailed.json`**
- **Purpose:** Complete incident metadata
- **Structure:**
```json
{
  "infra_1068|394354": {
    "incident_id": "infra_1068|394354",
    "registrar_id": "1068",
    "asn": "394354",
    "domain_count": 15,
    "cluster_count": 3,
    "domains": ["malicious1.com", "malicious2.com", ...],
    "pattern_set": [0, 1, 2]
  }
}
```

**4. `clustering_summary.json`**
- **Purpose:** Statistical summary of clustering run
- **Key Metrics:**
  - Total clusters found
  - Noise points count
  - Average cluster quality
  - Core clusters (quality ≥ 0.6 & persistence ≥ 0.5)
  - Algorithm contributions (DBSCAN vs HDBSCAN)

**5. `enrichment_report.json`**
- **Purpose:** Data quality assessment
- **Metrics:**
  - Overall enrichment quality
  - Feature presence rates
  - Recommendations for preset selection

**6. Visualizations**
- `clustering_pca.png` - 2D PCA projection of clusters
- `clustering_heatmap.png` - Distance matrix heatmap

---

## Step 7: Analyze Results

### Understanding Cluster Quality

**Quality Score Interpretation:**
- **0.0-0.4:** Low quality (filtered out by default)
- **0.4-0.6:** Medium quality (kept but may be noisy)
- **0.6-0.8:** Good quality (reliable clusters)
- **0.8-1.0:** Excellent quality (high confidence)

**Quality is computed using:**
- Average dissimilarity per feature (domain, subdomains, email, registrar, ASN)
- Cluster is "good" if ≥3 features have dissimilarity < 0.2

### Understanding Incident Grouping

**Infrastructure-Based Grouping:**
- Domains are grouped by shared `(registrar_id, ASN)` signature
- Each incident represents a potential threat actor's infrastructure
- Multiple clusters per incident indicate different campaign patterns

**Example Interpretation:**
```
incident_id: infra_1068|394354
- registrar_id: 1068 (Namecheap)
- asn: 394354 (CIRA-CLOUD2)
- clusters: [0, 1, 2] (3 different campaign patterns)
- domains: 15 total domains
```

This suggests 15 domains from the same infrastructure (registrar + ASN) form 3 distinct campaign clusters.

### Understanding Persistence Scores

**HDBSCAN Persistence:**
- Measures cluster stability across different density thresholds
- Range: [0, 1]
- Higher persistence = more stable cluster
- Clusters with persistence ≥ 0.5 are considered "core clusters"

---

## Step 8: Advanced Configuration

### Customize Weights Manually

Edit `domain_clustering/config/settings.py`:
```python
CONFIG["weights"] = [1.5, 1.2, 0.5, 2.5, 2.0]  # Custom weights
```

**Weight Order:**
1. Domain name
2. Subdomains
3. Email user
4. Registrar
5. ASN

### Adjust Quality Thresholds

Edit `domain_clustering/config/settings.py`:
```python
CONFIG["dbscan"]["filter_threshold"] = 0.50  # Stricter DBSCAN filtering
CONFIG["hdbscan"]["filter_threshold"] = 0.30  # Stricter HDBSCAN filtering
```

### Adjust Clustering Parameters

```python
CONFIG["dbscan"]["eps"] = 0.4  # Tighter DBSCAN clusters
CONFIG["dbscan"]["min_samples"] = 3  # Require more points per cluster
CONFIG["hdbscan"]["min_cluster_size"] = 3  # Larger minimum cluster size
```

---

## Troubleshooting

### Common Issues

**1. "No records after filtering"**
- **Cause:** Time window too restrictive or all timestamps invalid
- **Solution:** Increase `--window` or check timestamp columns

**2. "All domains marked as noise"**
- **Cause:** Distance threshold too strict or poor data quality
- **Solution:** 
  - Check enrichment quality report
  - Lower quality thresholds
  - Use `baseline` preset

**3. "Distance matrix computation slow"**
- **Cause:** Large dataset (>10,000 domains)
- **Solution:** 
  - Matrix is cached after first run
  - Consider sampling or time window filtering

**4. "Low enrichment quality warning"**
- **Cause:** Missing features (registrar, ASN, etc.)
- **Solution:**
  - Improve data enrichment
  - Use `conservative` preset
  - Adjust missing feature mode

---

## Programmatic Usage

**Python API:**
```python
from domain_clustering import run_pipeline, set_config_preset, CONFIG

# Set configuration
set_config_preset("practical")
CONFIG["time_window_days"] = 200

# Run pipeline
run_pipeline(
    enriched_path="enriched_domains_hq.csv",
    labeled_path=None,  # Optional
    config=CONFIG
)
```

---

## Next Steps

1. **Review Outputs:** Check `clustering_output/` for results
2. **Analyze Incidents:** Examine `incidents_detailed.json` for threat patterns
3. **Validate Clusters:** Review `clustering_results.csv` for domain assignments
4. **Tune Parameters:** Adjust weights/thresholds based on results
5. **Iterate:** Run with different presets to compare results

---

## Example Workflow

```bash
# 1. First run with defaults
python domain_clustering/main.py my_domains.csv

# 2. Check enrichment quality
cat clustering_output/enrichment_report.json

# 3. If quality is low, try conservative preset
python domain_clustering/main.py my_domains.csv --preset conservative

# 4. Compare results
diff clustering_output/clustering_results.csv clustering_output/clustering_results.csv

# 5. Analyze incidents
python -c "import json; print(json.dumps(json.load(open('clustering_output/incidents_detailed.json')), indent=2))"
```

---

## References

- **Architecture:** `domain_clustering/ARCHITECTURE.md`
- **Quick Start:** `QUICK_START.md`
- **Paper:** "Using DNS Patterns for Automated Cyber Threat Attribution" (Leite et al., 2024)
- **Quality Method:** Dupont et al. 2021 - "Similarity-Based Clustering For IoT Device Classification"
