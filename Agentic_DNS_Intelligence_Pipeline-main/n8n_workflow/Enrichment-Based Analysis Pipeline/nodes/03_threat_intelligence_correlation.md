# Threat Intelligence Correlation

## Purpose
Correlates enriched indicators with known threat intelligence knowledge.

## Description
This stage evaluates enrichment outputs against threat intelligence repositories to identify known associations, prior observations, or referenced activity.

Correlation emphasizes aggregation and consistency across sources, providing a consolidated intelligence view rather than isolated source-level signals.

## Inputs
- Enrichment dataset

## Outputs
- Correlated threat intelligence signals
- Attribution context (when available)

## Notes
Correlation results are treated as supporting evidence and are not interpreted as final determinations.
