# Feature Engineering: DNS-Based Infrastructure Signals

This folder contains scripts that transform raw domain indicators into
**structured, DNS-derived infrastructure features** suitable for clustering
and threat actor attribution.

This stage focuses on *feature engineering*, not workflow orchestration.
All domains—both actor-labeled and unknown—are processed using **identical
feature extraction logic**, ensuring fair and reproducible similarity
comparison.

## Engineered Features

Each domain is represented using the following infrastructure-level attributes:

- **Nameserver (NS) baseline**  
  Canonicalized base domains of authoritative nameservers, capturing operator
  preferences and infrastructure reuse.

- **Mail Exchanger (MX) baseline**  
  Normalized MX infrastructure used to identify shared email-handling services
  across campaigns.

- **SOA contact email**  
  Parsed and lowercased SOA email fields, which often persist across related
  infrastructure and are resistant to superficial domain churn.

- **Autonomous System Number (ASN)**  
  Hosting-level signal indicating preferred network providers and deployment
  environments.

- **Registrar information**  
  Domain registration behavior, which prior work shows can correlate with
  threat actor operational patterns.

- **IP co-hosting count**  
  Coarse bucket representing infrastructure density, emphasizing behavior over
  individual IP volatility.

## Design Principles

The feature engineering process follows several guiding principles:

- Favor **stable infrastructure behavior** over ephemeral indicators  
- Normalize multi-valued attributes into canonical sets  
- Reduce noise from transient hosting or DNS rotation  
- Preserve interpretability for analyst review and attribution validation

## Output

The feature engineering stage produces CSV files where each domain is encoded
as a structured feature vector. These outputs serve as the **direct input**
to the clustering and attribution components of the pipeline.
