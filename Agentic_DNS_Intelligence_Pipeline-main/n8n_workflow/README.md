# n8n Workflows

This directory contains all n8n-orchestrated pipeline implementations for the project.

Each subdirectory represents a **distinct pipeline derivation**, scoped and versioned independently.

## Current Pipelines

- `Enrichment-Based Analysis Pipeline/`  
  An enrichment-driven DNS intelligence pipeline where enrichment and LLM reasoning form the core analytical driver.

Only workflows contained inside this directory are considered executable pipelines.

## Requirements

To execute workflows under this directory, the following are required:

- A running n8n instance (local or hosted)
- Network access to external intelligence services used for enrichment
- Access to an LLM service for contextual reasoning
- File system access for report generation and persistence

Credentials, API keys, and environment-specific values are intentionally excluded from this repository and must be provided through the n8n environment.

## Notes

- This directory does not contain standalone application code.
- Language-level dependency specifications (for example, `requirements.txt` or `package.json`) are intentionally omitted.
- Pipeline-specific design and conceptual documentation are maintained within each pipeline’s directory.
