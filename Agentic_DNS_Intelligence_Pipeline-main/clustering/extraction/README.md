# Extraction: Threat Intelligence Ingestion

This folder contains scripts responsible for collecting domain-based Indicators of Compromise (IOCs) from open-source threat intelligence platforms. The extracted domains form the raw input to the enrichment and clustering pipeline.

## Data Sources

### AlienVault OTX
OTX is used to construct the **actor-labeled corpus**. Domains are extracted from public pulses associated with known threat actors and malware families. These domains serve as ground truth for attribution experiments.

Key characteristics:
- Actor or campaign context when available
- Community-curated intelligence
- Domain-level indicators only (URLs, hashes, and IP-only records are excluded)

### Abuse.ch ThreatFox
ThreatFox provides a continuously updated feed of malicious domains without explicit actor labels. These indicators represent **known malicious but actor-unknown infrastructure** and are used to populate the unlabeled dataset.

Key characteristics:
- High-frequency updates
- Behavioral and malware-type tags
- Confidence scores and timestamps

## Output

All extracted domains are normalized into a shared schema:
- `domain`
- `source` (OTX or ThreatFox)
- `actor` (when available)
- `tags`
- `timestamp`

The resulting CSV files are passed to the enrichment stage to ensure feature-space consistency across known and unknown domains.
