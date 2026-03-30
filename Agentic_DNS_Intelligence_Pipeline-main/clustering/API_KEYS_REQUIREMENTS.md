# API Keys and Data Sources: Clustering Pipeline

## Quick Answer

**The clustering pipeline itself does NOT need API keys.**

However, the **data enrichment step** (which happens BEFORE clustering) may or may not need API keys depending on which enrichment method you use.

---

## Clustering Pipeline: No API Keys Required

The clustering pipeline (`domain_clustering/main.py`) is a **pure computational process** that:

1. **Reads** already-enriched CSV/Parquet files
2. **Computes** distance matrices using mathematical algorithms
3. **Runs** clustering algorithms (DBSCAN/HDBSCAN)
4. **Outputs** cluster assignments and incident patterns

**It makes NO external API calls.** It only processes data that's already in your CSV/Parquet file.

---

## Data Enrichment: Depends on Method

Before you can run clustering, you need **enriched data**. There are multiple ways to enrich domains, and API key requirements differ:

### Option 1: Basic Enrichment (NO API Keys) ✅

**Script:** `clustering/feature_engineering/domain_enrichment.py`

**What it does:**
- DNS resolution (A records) - uses `dns.resolver` (public DNS)
- WHOIS lookup - uses `python-whois` (public WHOIS servers)
- ASN lookup - uses `ipwhois` (public RDAP/WHOIS)

**API Keys Required:** ❌ **NONE**

**Usage:**
```bash
# Enrich single domain
python clustering/feature_engineering/domain_enrichment.py --domain example.com

# Enrich CSV file
python clustering/feature_engineering/domain_enrichment.py \
  --input-csv domains.csv \
  --output-csv enriched_domains.csv
```

**What you get:**
- Domain, IPs, ASN, ASN description, ASN country
- Registrar, creation_date, expiration_date
- SLD, TLD

**Limitations:**
- Basic WHOIS data only
- No threat intelligence (VirusTotal, OTX)
- No advanced enrichment features

---

### Option 2: n8n Workflow Enrichment (API Keys Required) ⚠️

**Method:** n8n workflow webhook

**What it does:**
- VirusTotal API - threat intelligence
- AlienVault OTX API - threat actor attribution
- WhoIsFreaks API - enhanced WHOIS data

**API Keys Required:** ✅ **YES**

**Required API Keys:**
1. **VirusTotal API Key** (`x-apikey` header)
   - Get from: https://www.virustotal.com/gui/join-us
   - Free tier: 4 requests/minute
   - Paid tier: Higher rate limits

2. **AlienVault OTX API Key** (`X-OTX-API-KEY` header)
   - Get from: https://otx.alienvault.com/api
   - Free tier: Available
   - Requires account registration

3. **WhoIsFreaks API Key** (`apiKey` parameter)
   - Get from: https://whoisfreaks.com/
   - Free tier: Limited requests
   - Paid tier: Higher limits

**Usage:**
```bash
# Trigger n8n workflow
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d '{"domains": ["example.com"]}'
```

**What you get:**
- All basic enrichment (DNS, WHOIS, ASN)
- **PLUS:** VirusTotal threat scores
- **PLUS:** OTX threat actor attribution
- **PLUS:** Enhanced WHOIS data
- **PLUS:** LLM-generated threat intelligence report

**Advantages:**
- Comprehensive threat intelligence
- Threat actor attribution
- Automated report generation

---

### Option 3: Extraction Scripts (API Keys Required) ⚠️

**Scripts:**
- `clustering/extraction/otx/pull_actor_domains.py` - OTX API
- `clustering/extraction/threatfox/pull_threatfox_domains.py` - ThreatFox API

**What it does:**
- Pulls threat intelligence data from OSINT sources
- Extracts actor-labeled domains
- Builds domain datasets

**API Keys Required:** ✅ **YES**

**Required API Keys:**
1. **OTX API Key** (for `pull_actor_domains.py`)
   - Same as n8n workflow
   - Stored in `.env` file: `OTX_API_KEY=your_key`

2. **ThreatFox API Key** (for `pull_threatfox_domains.py`)
   - Get from: https://threatfox.abuse.ch/api/
   - Free tier: Available

**Usage:**
```bash
# Set up .env file
echo "OTX_API_KEY=your_key_here" > .env

# Run extraction
python clustering/extraction/otx/pull_actor_domains.py
```

---

## Complete Workflow Examples

### Workflow 1: No API Keys (Basic)

```bash
# Step 1: Enrich domains (no API keys needed)
python clustering/feature_engineering/domain_enrichment.py \
  --input-csv raw_domains.csv \
  --output-csv enriched_domains.csv

# Step 2: Run clustering (no API keys needed)
python clustering/domain_clustering/main.py enriched_domains.csv
```

**Result:** Basic clustering with DNS/WHOIS/ASN features only

---

### Workflow 2: With API Keys (Comprehensive)

```bash
# Step 1: Enrich via n8n workflow (requires API keys)
# Configure API keys in n8n UI first, then:
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d '{"domains": ["domain1.com", "domain2.com"]}'

# Step 2: Collect enriched data from n8n outputs
# (Save to CSV manually or via script)

# Step 3: Run clustering (no API keys needed)
python clustering/domain_clustering/main.py enriched_from_n8n.csv
```

**Result:** Clustering with full threat intelligence enrichment

---

### Workflow 3: Hybrid Approach

```bash
# Step 1: Basic enrichment (no API keys)
python clustering/feature_engineering/domain_enrichment.py \
  --input-csv domains.csv \
  --output-csv basic_enriched.csv

# Step 2: Run clustering (no API keys)
python clustering/domain_clustering/main.py basic_enriched.csv

# Step 3: (Optional) Enhance with threat intelligence later
# Use n8n workflow for specific domains of interest
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│ Raw Domains (CSV)                                       │
└─────────────────────────────────────────────────────────┘
                    ↓
    ┌───────────────────────────────┐
    │ ENRICHMENT STEP                │
    │ (Choose one method)            │
    └───────────────────────────────┘
                    ↓
    ┌───────────────┴───────────────┐
    │                               │
    ▼                               ▼
┌──────────────┐          ┌──────────────────┐
│ Basic        │          │ n8n Workflow     │
│ Enrichment   │          │ (with API keys)  │
│              │          │                  │
│ NO API KEYS  │          │ API KEYS NEEDED  │
│              │          │ - VirusTotal     │
│ Uses:        │          │ - OTX            │
│ - DNS        │          │ - WhoIsFreaks    │
│ - WHOIS      │          │                  │
│ - ASN        │          │                  │
└──────────────┘          └──────────────────┘
    │                               │
    └───────────────┬───────────────┘
                    ↓
    ┌───────────────────────────────┐
    │ Enriched CSV/Parquet File     │
    └───────────────────────────────┘
                    ↓
    ┌───────────────────────────────┐
    │ CLUSTERING PIPELINE            │
    │                                │
    │ NO API KEYS NEEDED             │
    │                                │
    │ - Reads CSV                    │
    │ - Computes distances           │
    │ - Runs clustering              │
    │ - Outputs results              │
    └───────────────────────────────┘
                    ↓
    ┌───────────────────────────────┐
    │ clustering_output/             │
    │ - clustering_results.csv       │
    │ - campaign_patterns.csv         │
    │ - incidents_detailed.json      │
    └───────────────────────────────┘
```

---

## Summary Table

| Component | API Keys Required | What It Does |
|-----------|------------------|--------------|
| **Clustering Pipeline** | ❌ NO | Reads CSV, computes clusters |
| **Basic Enrichment** | ❌ NO | DNS, WHOIS, ASN (public sources) |
| **n8n Workflow** | ✅ YES | VirusTotal, OTX, WhoIsFreaks |
| **OTX Extraction** | ✅ YES | Pulls actor-labeled domains |
| **ThreatFox Extraction** | ✅ YES | Pulls threat intelligence |

---

## Getting API Keys (If Needed)

### VirusTotal
1. Sign up: https://www.virustotal.com/gui/join-us
2. Go to: https://www.virustotal.com/gui/user/your_username/apikey
3. Copy API key
4. Free tier: 4 requests/minute, 500/day

### AlienVault OTX
1. Sign up: https://otx.alienvault.com/
2. Go to: https://otx.alienvault.com/api
3. Generate API key
4. Free tier: Available

### WhoIsFreaks
1. Sign up: https://whoisfreaks.com/
2. Go to API section
3. Generate API key
4. Free tier: Limited requests

### ThreatFox
1. Sign up: https://threatfox.abuse.ch/
2. Go to: https://threatfox.abuse.ch/api/
3. Generate API key
4. Free tier: Available

---

## Recommendations

### For Testing/Development
- **Use basic enrichment** (no API keys)
- Fast, no rate limits
- Good for understanding the clustering process

### For Production/Research
- **Use n8n workflow** (with API keys)
- Comprehensive threat intelligence
- Better attribution capabilities
- Automated report generation

### For Large-Scale Analysis
- **Use extraction scripts** to build datasets
- **Use basic enrichment** for bulk processing
- **Use n8n workflow** for specific high-value domains

---

## Troubleshooting

### "No API key found"
- **Cause:** Trying to use n8n workflow or extraction scripts without API keys
- **Solution:** Either:
  1. Get API keys and configure them
  2. Use basic enrichment instead (no API keys)

### "Rate limit exceeded"
- **Cause:** Too many API requests (VirusTotal, OTX)
- **Solution:** 
  - Add delays between requests
  - Use basic enrichment for bulk processing
  - Upgrade to paid API tier

### "Enrichment incomplete"
- **Cause:** API failures or missing keys
- **Solution:**
  - Check API key configuration
  - Verify network connectivity
  - Use basic enrichment as fallback

---

## Key Takeaways

1. ✅ **Clustering pipeline never needs API keys** - it's pure computation
2. ⚠️ **Enrichment may need API keys** - depends on method chosen
3. ✅ **Basic enrichment works without API keys** - uses public DNS/WHOIS
4. ⚠️ **n8n workflow requires API keys** - for threat intelligence
5. ✅ **You can mix approaches** - basic for bulk, n8n for specific domains

---

## References

- Basic Enrichment: `clustering/feature_engineering/domain_enrichment.py`
- n8n Workflow: `n8n_workflow/Enrichment-Based Analysis Pipeline/`
- Extraction Scripts: `clustering/extraction/`
- Clustering Pipeline: `clustering/domain_clustering/main.py`
