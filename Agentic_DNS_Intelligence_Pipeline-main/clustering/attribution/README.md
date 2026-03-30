# Attribution: Actor Similarity and Confidence Scoring

> **Scope note**  
> The attribution approach described in this directory is under research and development, and further testing is being done.  
> It is **not currently integrated** into the active n8n-based enrichment pipeline and is documented here to explain the proposed methodology and design.

This folder implements the attribution logic that maps clustered, unlabeled domains to known threat actors based on DNS infrastructure similarity.

Attribution is performed **after clustering**, using aggregated behavioral fingerprints rather than individual domains.

## Attribution Strategy

### 1. Actor Fingerprints
Known actor domains (from OTX) are enriched and grouped by actor label. For each actor, recurring DNS features are aggregated into an infrastructure fingerprint representing long-term operational behavior.

### 2. Cluster-Level Comparison
Each unknown cluster is compared against all actor fingerprints using feature-level set overlap. This approach allows attribution even when individual domains are short-lived or partially observed.

### 3. Weighted Similarity
For each feature (e.g., NS, SOA, ASN, registrar), a Jaccard similarity score is computed. Feature-specific weights emphasize infrastructure attributes shown to be stable across campaigns.

The final confidence score is a weighted average normalized to the range [0, 1] and reported as a percentage.

## Confidence Interpretation

- **High confidence**: Strong, multi-feature overlap with a known actor fingerprint  
- **Low confidence**: Sparse or inconsistent overlap  
- **Unknown**: Insufficient evidence or generic infrastructure patterns

## Ambiguity Handling

The system avoids forced attribution:
- Multiple candidates may be returned when similarities are comparable
- Clusters with weak evidence are labeled as *Unknown*
- Confidence scores explicitly encode uncertainty

## Output

Attribution results are saved as CSV files containing:
- Unknown cluster ID
- Candidate actor labels
- Feature overlap scores
- Final confidence score
- Decision rationale

This conservative design aligns with best practices in operational threat intelligence and academic attribution research.
