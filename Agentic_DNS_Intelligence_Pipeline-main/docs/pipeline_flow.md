# Pipeline Flow

1. **Domain Input**
   - A list of domains is provided as input.

2. **Enrichment**
   - VirusTotal: reputation, detections, categories.
   - OTX: pulses, tags, related indicators.
   - Whois: registrar, creation date, nameservers.

3. **Merge & Normalize**
   - All enrichment results for each domain are merged into a single JSON object.

4. **LLM Evaluation**
   - Produces:
     - risk level (benign / suspicious / malicious),
     - malicious suspicion percentage,
     - category (e.g., phishing, C2),
     - behavioral tags,
     - short explanation.

5. **Report Generation**
   - Results are formatted into a human-readable report (HTML/PDF).

6. **Output**
   - Reports and JSON outputs are stored under the `results/` structure.
