# Architecture Overview

The Agentic DNS Intelligence Pipeline consists of the following conceptual components:

1. **Input / Domain ingestion**
2. **Enrichment engines**
   - VirusTotal
   - OTX AlienVault
   - Whois
3. **Merge / normalization layer**
4. **LLM analysis**
   - Risk classification
   - Suspicion percentage
   - Behavioral / threat tags
5. **Report generation**
6. **Result storage (reports and JSON)**

Clustering is planned for a future phase and will be added after the enrichment
merge stage.
