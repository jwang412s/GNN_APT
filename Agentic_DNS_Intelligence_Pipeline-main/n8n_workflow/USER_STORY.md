# User Story: n8n Workflow Trigger and Execution

This document explains how the n8n-based DNS Intelligence Pipeline is triggered, how webhooks work, and how users interact with the system.

---

## Overview: Two Separate Systems

This repository contains **two distinct systems** with different interfaces:

1. **n8n Workflow (Enrichment-Based Pipeline)** - Webhook-triggered, HTTP-based
2. **Clustering Pipeline** - CLI-based, command-line interface

This document focuses on the **n8n workflow system**.

---

## System Architecture

### n8n Workflow System

**Interface Type:** HTTP Webhook (REST API)  
**No GUI Application:** The system does NOT have a standalone web application or desktop app  
**Trigger Method:** HTTP POST request to webhook endpoint  
**Orchestration:** n8n workflow automation platform

---

## How the Webhook Gets Triggered

### 1. n8n Instance Setup

**Prerequisites:**
- n8n must be installed and running (local or cloud-hosted)
- Workflow must be imported and activated in n8n
- n8n webhook URL must be accessible

**Default n8n Setup:**
- Local: `http://localhost:5678`
- Cloud: Your n8n cloud instance URL

### 2. Webhook Configuration

The workflow defines a webhook node with:
- **HTTP Method:** POST
- **Path:** `/dnsintel`
- **Full URL:** `http://localhost:5678/webhook/dnsintel` (local) or `https://your-instance.n8n.io/webhook/dnsintel` (cloud)

**From the workflow JSON:**
```json
{
  "type": "n8n-nodes-base.webhook",
  "parameters": {
    "httpMethod": "POST",
    "path": "dnsintel",
    "responseMode": "responseNode"
  }
}
```

### 3. Triggering the Workflow

**The workflow is triggered by sending an HTTP POST request to the webhook URL.**

**No Application Interface Required:**
- No web UI to click buttons
- No desktop application
- No mobile app
- Just HTTP requests (curl, Postman, Python requests, etc.)

---

## User Story: Triggering the Workflow

### Scenario 1: Using cURL (Command Line)

**Step 1: Start n8n (if running locally)**
```bash
# If using Docker
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  n8nio/n8n

# Or if installed via npm
npx n8n
```

**Step 2: Import the Workflow**
1. Open n8n UI: `http://localhost:5678`
2. Import workflow from: `n8n_workflow/Enrichment-Based Analysis Pipeline/config/Agentic-AI DNS Intelligence Pipeline.json`
3. Activate the workflow (toggle switch)

**Step 3: Get the Webhook URL**
- In n8n UI, click on the "Webhook" node
- Copy the webhook URL (e.g., `http://localhost:5678/webhook/dnsintel`)

**Step 4: Trigger via cURL**
```bash
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d '{
    "domains": ["malicious-domain.com"]
  }'
```

**Expected Response:**
- Workflow executes asynchronously
- Returns HTTP 200 with execution status
- Report is generated and saved to disk
- Final response includes report location

### Scenario 2: Using Python Script

```python
import requests
import json

# Webhook URL
webhook_url = "http://localhost:5678/webhook/dnsintel"

# Payload
payload = {
    "domains": ["suspicious-domain.com", "another-domain.net"]
}

# Send POST request
response = requests.post(
    webhook_url,
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload)
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
```

### Scenario 3: Using Postman

1. **Create New Request:**
   - Method: POST
   - URL: `http://localhost:5678/webhook/dnsintel`

2. **Set Headers:**
   - `Content-Type: application/json`

3. **Set Body (raw JSON):**
   ```json
   {
     "domains": ["test-domain.com"]
   }
   ```

4. **Send Request:**
   - Click "Send"
   - View response in Postman

### Scenario 4: Integration with Other Systems

**From SIEM/Security Tools:**
```bash
# Example: Splunk HTTP Event Collector integration
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d @suspicious_domains.json
```

**From Monitoring Systems:**
- Configure webhook alerts to trigger n8n workflow
- Send domain indicators automatically when detected

**From CI/CD Pipelines:**
```yaml
# Example: GitHub Actions
- name: Trigger DNS Analysis
  run: |
    curl -X POST ${{ secrets.N8N_WEBHOOK_URL }} \
      -H "Content-Type: application/json" \
      -d '{"domains": ["${{ github.event.head_commit.message }}"]}'
```

---

## Workflow Execution Flow

### What Happens When Webhook is Triggered

```
1. HTTP POST → Webhook Node
   ↓
2. Split Out Domains (if multiple)
   ↓
3. Parallel Enrichment:
   - VirusTotal API
   - AlienVault OTX API
   - WhoIsFreaks API
   ↓
4. Data Merging & Schema Lock
   ↓
5. Enrichment Check
   ├─ If NOT enriched → Early Response
   └─ If enriched → Continue
   ↓
6. LLM Reasoning (Contextual Analysis)
   ↓
7. Normalizing (Data Processing)
   ↓
8. Convert to HTML (Report Generation)
   ↓
9. Write to Disk (Save Report)
   ↓
10. Respond to Webhook (Return Results)
```

### Request Format

**Input:**
```json
{
  "domains": ["domain1.com", "domain2.net"]
}
```

**Output (Response):**
```json
{
  "status": "completed",
  "report_path": "/path/to/report.html",
  "domains_analyzed": ["domain1.com", "domain2.net"],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Access Methods Summary

### ✅ Available Methods

1. **Command Line (cURL)**
   - Direct HTTP POST requests
   - Scriptable and automatable
   - No GUI needed

2. **Programming Languages**
   - Python `requests` library
   - Node.js `axios` or `fetch`
   - Any HTTP client library

3. **API Testing Tools**
   - Postman
   - Insomnia
   - HTTPie

4. **Integration Platforms**
   - Zapier (if n8n cloud)
   - Make (formerly Integromat)
   - Custom integrations

5. **Security Tools**
   - SIEM systems (Splunk, ELK)
   - SOAR platforms
   - Security monitoring tools

### ❌ NOT Available

- **No Web Application UI**
  - No browser-based interface to submit domains
  - No dashboard to view results
  - No login/authentication system

- **No Desktop Application**
  - No standalone GUI application
  - No mobile app
  - No native client

- **No CLI Tool**
  - The n8n workflow is NOT triggered via command line
  - (The clustering pipeline has CLI, but that's separate)

---

## n8n UI vs. Webhook Interface

### n8n UI (Workflow Management)

**Purpose:** Configure and manage workflows

**Access:**
- URL: `http://localhost:5678` (local) or your n8n cloud URL
- Used for:
  - Importing workflows
  - Editing workflow logic
  - Viewing execution history
  - Managing credentials
  - Testing workflows manually

**NOT for:** End-user domain analysis (that's done via webhook)

### Webhook Interface (Execution)

**Purpose:** Trigger workflow execution

**Access:**
- URL: `http://localhost:5678/webhook/dnsintel`
- Used for:
  - Sending domain indicators
  - Triggering analysis
  - Getting results

**This is the "user-facing" interface** (even though it's programmatic)

---

## Complete User Journey Example

### Step-by-Step: First-Time Setup

**1. Install n8n**
```bash
# Option A: Docker
docker pull n8nio/n8n
docker run -it --rm -p 5678:5678 n8nio/n8n

# Option B: npm
npm install n8n -g
n8n start
```

**2. Access n8n UI**
- Open browser: `http://localhost:5678`
- Create account (first time only)

**3. Import Workflow**
- Click "Workflows" → "Import from File"
- Select: `n8n_workflow/Enrichment-Based Analysis Pipeline/config/Agentic-AI DNS Intelligence Pipeline.json`
- Workflow appears in your list

**4. Configure Credentials**
- Add API keys for:
  - VirusTotal (x-apikey)
  - AlienVault OTX (X-OTX-API-KEY)
  - WhoIsFreaks (apiKey)
  - LLM service (if using external LLM)

**5. Activate Workflow**
- Toggle the "Active" switch ON
- Workflow is now listening for webhook requests

**6. Get Webhook URL**
- Click on "Webhook" node in workflow
- Copy the webhook URL shown
- Example: `http://localhost:5678/webhook/dnsintel`

**7. Test the Webhook**
```bash
curl -X POST http://localhost:5678/webhook/dnsintel \
  -H "Content-Type: application/json" \
  -d '{"domains": ["test.com"]}'
```

**8. Check Results**
- View execution in n8n UI (Executions tab)
- Check report output location
- Reports are typically saved to disk (path configured in workflow)

---

## Production Deployment

### Cloud Deployment (n8n Cloud)

**Benefits:**
- Persistent webhook URLs
- No local server management
- Built-in authentication
- Scalable

**Setup:**
1. Sign up at `https://n8n.io`
2. Import workflow
3. Configure credentials
4. Activate workflow
5. Use cloud webhook URL: `https://your-instance.n8n.io/webhook/dnsintel`

### Self-Hosted Deployment

**Options:**
- Docker container
- Kubernetes deployment
- VPS/server installation
- Requires:
  - Public IP or domain
  - Port forwarding (if behind firewall)
  - SSL certificate (for HTTPS)

**Webhook URL Format:**
- HTTP: `http://your-server-ip:5678/webhook/dnsintel`
- HTTPS: `https://your-domain.com/webhook/dnsintel`

---

## Security Considerations

### Webhook Security

**Current State:**
- Webhook is publicly accessible (if n8n is exposed)
- No authentication by default
- Anyone with the URL can trigger it

**Recommendations:**
1. **Use n8n Cloud** (built-in security)
2. **Add Authentication:**
   - Configure webhook authentication in n8n
   - Use API keys or OAuth
3. **Network Security:**
   - Keep n8n behind firewall
   - Use VPN for access
   - Restrict webhook access by IP
4. **Rate Limiting:**
   - Configure rate limits in n8n
   - Prevent abuse

### API Key Management

**Store Securely:**
- Use n8n's credential management
- Never commit API keys to repository
- Rotate keys regularly

---

## Comparison: n8n Workflow vs. Clustering Pipeline

| Feature | n8n Workflow | Clustering Pipeline |
|---------|-------------|-------------------|
| **Interface** | HTTP Webhook | CLI (command line) |
| **Trigger** | POST request | `python main.py` |
| **Input** | JSON with domains | CSV/Parquet file |
| **Output** | HTML report | CSV/JSON results |
| **Purpose** | Real-time analysis | Batch clustering |
| **Use Case** | Single domain analysis | Bulk domain clustering |
| **Integration** | API | Script |
| **Integration Status** | ✅ Operational | ⚠️ Not integrated (Phase 3 planned) |

**Note:** The clustering pipeline is NOT currently integrated with the n8n workflow. Integration is planned for Phase 3.

---

## Troubleshooting

### Common Issues

**1. "Webhook not found"**
- **Cause:** Workflow not activated
- **Solution:** Toggle "Active" switch in n8n UI

**2. "Connection refused"**
- **Cause:** n8n not running
- **Solution:** Start n8n service

**3. "Timeout"**
- **Cause:** Enrichment APIs slow or rate-limited
- **Solution:** Check API status, add retry logic

**4. "Invalid domain format"**
- **Cause:** Malformed JSON or domain string
- **Solution:** Validate input format

**5. "Missing API keys"**
- **Cause:** Credentials not configured
- **Solution:** Add API keys in n8n credentials

---

## Example Integration Scripts

### Python Wrapper

```python
#!/usr/bin/env python3
"""
Simple wrapper to trigger n8n DNS Intelligence workflow
"""

import requests
import sys
import json

N8N_WEBHOOK_URL = "http://localhost:5678/webhook/dnsintel"

def analyze_domain(domain):
    """Send domain to n8n workflow for analysis"""
    payload = {"domains": [domain]}
    
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=300  # 5 minutes
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python trigger_analysis.py <domain>")
        sys.exit(1)
    
    domain = sys.argv[1]
    result = analyze_domain(domain)
    
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Analysis failed")
```

### Bash Script

```bash
#!/bin/bash
# trigger_dns_analysis.sh

WEBHOOK_URL="http://localhost:5678/webhook/dnsintel"

if [ -z "$1" ]; then
    echo "Usage: $0 <domain>"
    exit 1
fi

DOMAIN="$1"

curl -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"domains\": [\"$DOMAIN\"]}" \
  | jq '.'
```

---

## Summary

**Key Points:**

1. **No Application Interface:** The system uses HTTP webhooks, not a GUI app
2. **Webhook-Based:** Triggered via HTTP POST requests
3. **Programmatic Access:** Use curl, Python, Postman, or any HTTP client
4. **n8n UI:** Only for workflow management, not for end-user analysis
5. **Separate Systems:** n8n workflow (webhook) and clustering pipeline (CLI) are separate

**To Use the System:**
1. Set up n8n (local or cloud)
2. Import and activate the workflow
3. Send HTTP POST requests to the webhook URL
4. Receive analysis results

**Future Integration (Phase 3):**
- REST API endpoints for clustering (planned)
- Integration between n8n workflow and clustering pipeline
- Unified interface (possibly web-based)
