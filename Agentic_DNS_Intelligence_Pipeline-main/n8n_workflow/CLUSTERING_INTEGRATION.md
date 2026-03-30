# n8n Workflow and Clustering Integration Status

## Current Status: **NOT INTEGRATED**

**The n8n workflow does NOT currently use or integrate with the clustering pipeline.**

These are **two separate, independent systems** that operate independently:

1. **n8n Workflow** - Enrichment-based, real-time analysis
2. **Clustering Pipeline** - Batch clustering, threat actor attribution

---

## Why They're Separate

### Different Use Cases

| Aspect | n8n Workflow | Clustering Pipeline |
|--------|-------------|-------------------|
| **Purpose** | Real-time domain analysis | Batch threat actor attribution |
| **Input** | Single or few domains (JSON) | Large dataset (CSV/Parquet) |
| **Output** | HTML threat intelligence report | Cluster assignments, incident patterns |
| **Execution** | On-demand (webhook trigger) | Batch processing (CLI) |
| **Analysis Type** | Enrichment + LLM reasoning | Distance-based clustering |
| **Time Scale** | Seconds to minutes | Minutes to hours |

### Different Analytical Approaches

**n8n Workflow (Enrichment-Based):**
- Focuses on **external intelligence sources**
- Uses VirusTotal, AlienVault OTX, WhoIsFreaks APIs
- Applies LLM reasoning for contextual analysis
- Generates narrative reports
- **Best for:** Single domain investigation, real-time threat assessment

**Clustering Pipeline:**
- Focuses on **pattern discovery**
- Uses distance metrics (Levenshtein, Jaccard, etc.)
- Applies DBSCAN/HDBSCAN clustering algorithms
- Groups domains by infrastructure similarity
- **Best for:** Bulk analysis, campaign detection, threat actor attribution

---

## Current n8n Workflow Flow

The n8n workflow **does not include any clustering steps**. Current flow:

```
1. Webhook receives domain(s)
   ↓
2. Parallel Enrichment:
   - VirusTotal API
   - AlienVault OTX API  
   - WhoIsFreaks API
   ↓
3. Data Merging
   ↓
4. Enrichment Check
   ↓
5. LLM Reasoning (if enriched)
   ↓
6. Report Generation (HTML)
   ↓
7. Save & Respond
```

**No clustering nodes exist in the workflow JSON.**

---

## What Integration Would Look Like (Phase 3)

### Planned Integration Architecture

Based on the placeholder code in `clustering/domain_clustering/pipeline/n8n_interface.py`, future integration would include:

**1. REST API Endpoints:**
```python
# Planned endpoints (not yet implemented)
- POST /api/clustering/run - Run clustering on dataset
- GET /api/clustering/metrics - Get clustering statistics
- POST /api/incidents/build - Build incidents from clusters
- GET /api/quality/evaluate/{cluster_id} - Evaluate cluster quality
```

**2. n8n Workflow Integration Options:**

**Option A: Clustering as a Node**
```
Enrichment → Data Collection → Clustering Node → Enhanced Report
```

**Option B: Separate Clustering Workflow**
```
Trigger Clustering Workflow → Process Batch → Return Results → Use in Analysis
```

**Option C: Hybrid Approach**
```
Real-time Analysis (n8n) → Store Results → Periodic Clustering → Update Attribution
```

### Example: How It Could Work

**Scenario: Enhanced Attribution**

1. **n8n workflow receives domain:**
   ```json
   {"domains": ["suspicious-domain.com"]}
   ```

2. **Enrichment phase (current):**
   - VirusTotal, OTX, WhoIsFreaks enrichment
   - LLM reasoning

3. **NEW: Clustering lookup phase:**
   - Check if domain belongs to known cluster
   - Retrieve cluster metadata (incident_id, related domains)
   - Get cluster quality score
   - Find similar incidents

4. **Enhanced report generation:**
   - Include cluster attribution
   - Show related domains from same campaign
   - Display infrastructure patterns
   - Provide threat actor attribution

**Example Enhanced Report:**
```
DNS Intelligence Report — suspicious-domain.com

[Standard enrichment analysis...]

Cluster Attribution:
- Cluster ID: 42
- Cluster Quality: 0.85 (High)
- Incident: infra_1068|394354
- Related Domains: 15 domains in same cluster
- Attribution: Likely part of "Operation X" campaign
- Infrastructure: Namecheap (ID: 1068), ASN: 394354
```

---

## Why Integration Is Complex

### Technical Challenges

1. **Different Execution Models:**
   - n8n: Event-driven, real-time
   - Clustering: Batch processing, computationally intensive

2. **Different Data Formats:**
   - n8n: JSON, single domain at a time
   - Clustering: CSV/Parquet, requires bulk dataset

3. **Performance Considerations:**
   - Clustering requires distance matrix computation (O(n²))
   - Not suitable for real-time single-domain analysis
   - Needs pre-computed clusters or lookup tables

4. **Architecture Mismatch:**
   - n8n: Orchestration platform (low-code)
   - Clustering: Python library (code-based)

### Integration Strategies

**Strategy 1: Pre-computed Clusters**
- Run clustering periodically on collected domains
- Store cluster assignments in database
- n8n workflow queries database for cluster info
- **Pros:** Fast, real-time compatible
- **Cons:** Stale data, requires periodic updates

**Strategy 2: Clustering Service**
- Deploy clustering as microservice (REST API)
- n8n calls clustering API with enriched data
- **Pros:** Modular, scalable
- **Cons:** Latency, requires service infrastructure

**Strategy 3: Hybrid Batch + Lookup**
- Clustering runs on batch of domains
- Results stored in lookup database
- n8n queries for cluster membership
- **Pros:** Best of both worlds
- **Cons:** Complex architecture

---

## Current Workarounds (Manual Integration)

### Option 1: Sequential Execution

**Step 1: Run n8n workflow to enrich domains**
```bash
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d '{"domains": ["domain1.com", "domain2.com"]}'
```

**Step 2: Collect enriched data**
- Save enriched domains to CSV
- Aggregate results from multiple n8n runs

**Step 3: Run clustering on collected data**
```bash
python clustering/domain_clustering/main.py enriched_domains.csv
```

**Step 4: Use clustering results**
- Review `clustering_output/clustering_results.csv`
- Cross-reference with n8n reports

### Option 2: Script-Based Integration

**Python script that combines both:**

```python
#!/usr/bin/env python3
"""
Manual integration: n8n enrichment + clustering
"""

import requests
import pandas as pd
from domain_clustering import run_pipeline

# Step 1: Enrich domains via n8n
domains = ["domain1.com", "domain2.com", "domain3.com"]
enriched_data = []

for domain in domains:
    response = requests.post(
        "http://localhost:5678/webhook/dnsintel",
        json={"domains": [domain]}
    )
    # Extract enrichment data from response
    enriched_data.append(extract_enrichment_data(response))

# Step 2: Save to CSV
df = pd.DataFrame(enriched_data)
df.to_csv("enriched_for_clustering.csv", index=False)

# Step 3: Run clustering
run_pipeline("enriched_for_clustering.csv")

# Step 4: Combine results
clustering_results = pd.read_csv("clustering_output/clustering_results.csv")
# Merge with n8n reports
```

---

## Future Integration Plans (Phase 3)

### Planned Components

**1. REST API Interface** (`n8n_interface.py`)
- Flask/FastAPI endpoints
- Clustering operations as HTTP services
- Incident query endpoints
- Quality evaluation endpoints

**2. n8n Workflow Nodes**
- "Clustering Lookup" node
- "Cluster Attribution" node
- "Incident Pattern" node

**3. Database Integration**
- Store cluster assignments
- Cache distance matrices
- Maintain incident metadata

**4. Real-time Clustering**
- Incremental clustering updates
- Stream processing integration
- Event-driven cluster updates

---

## Use Case Comparison

### When to Use n8n Workflow (Current)

✅ **Use n8n workflow when:**
- Analyzing single or few domains
- Need real-time threat assessment
- Want narrative reports
- Focus on external intelligence
- Quick turnaround needed

**Example:**
- SOC analyst receives suspicious domain
- Needs immediate threat assessment
- Wants human-readable report

### When to Use Clustering Pipeline (Current)

✅ **Use clustering pipeline when:**
- Analyzing large dataset (100+ domains)
- Need threat actor attribution
- Looking for campaign patterns
- Infrastructure-based grouping
- Batch processing acceptable

**Example:**
- Security researcher has 1000 domains
- Wants to identify threat actor campaigns
- Needs to group by infrastructure
- Can wait for batch processing

### When Integration Would Help

✅ **Use integrated system when:**
- Need both real-time analysis AND attribution
- Want to leverage cluster context in reports
- Need to identify related domains quickly
- Require infrastructure-based attribution
- Want automated threat actor identification

**Example:**
- SOC analyst receives domain
- System checks if domain belongs to known cluster
- Report includes: "This domain is part of Cluster 42, linked to 15 other malicious domains, attributed to Threat Actor X"

---

## Summary

### Current State

- ❌ **n8n workflow does NOT use clustering**
- ❌ **No integration exists**
- ✅ **Both systems work independently**
- ✅ **Each serves different use cases**

### Key Points

1. **Separate Systems:** They are intentionally separate due to different use cases
2. **No Integration Code:** No clustering nodes in n8n workflow JSON
3. **Placeholder Only:** `n8n_interface.py` is a Phase 3 placeholder
4. **Manual Workaround:** Can run both sequentially, but not automated
5. **Future Plans:** Integration planned for Phase 3

### How to Use Both Today

1. **For real-time analysis:** Use n8n workflow
2. **For batch clustering:** Use clustering pipeline CLI
3. **For combined analysis:** Run both manually and combine results

### Future Vision

- Integrated system where n8n workflow can:
  - Query cluster database for attribution
  - Include cluster context in reports
  - Trigger clustering on collected domains
  - Provide threat actor attribution automatically

---

## References

- Clustering README: `clustering/README.md`
- n8n Workflow README: `n8n_workflow/README.md`
- Clustering Architecture: `clustering/domain_clustering/ARCHITECTURE.md`
- n8n Interface Placeholder: `clustering/domain_clustering/pipeline/n8n_interface.py`
