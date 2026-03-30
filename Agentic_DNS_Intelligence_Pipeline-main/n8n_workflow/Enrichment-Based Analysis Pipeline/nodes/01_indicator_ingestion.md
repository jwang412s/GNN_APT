# Indicator Ingestion

## Purpose
Accepts domain indicators through a controlled entry point and prepares them for downstream analysis.

## Description
This stage is responsible for receiving domain indicators, validating basic structure, and normalizing values into a consistent internal representation.

Preprocessing focuses on correctness and consistency rather than analysis. No judgment or scoring is performed at this stage.

## Inputs
- Raw domain indicator (string)

## Outputs
- Normalized domain indicator
- Ingestion metadata (timestamp, source)

## Notes
This stage serves as the stable entry point for all pipeline derivations.
