# Configuration

This directory contains configuration artifacts used by the enrichment-based analysis pipeline.

The primary artifact in this directory is the n8n workflow definition, which represents the **authoritative execution configuration** of the pipeline.

## Contents

- Workflow configuration files intended to be imported directly into n8n
- Non-sensitive configuration examples provided for reference

## Scope and Intent

Files in this directory define **how the pipeline is orchestrated**, not how it is conceptually documented.

- The workflow JSON is the source of truth for execution behavior
- Conceptual pipeline stages are documented separately under `nodes/`
- Extracted JavaScript logic (when applicable) is documented separately under `code/`

## Notes

- Secrets, credentials, and environment-specific values are intentionally excluded
- Any changes to execution logic should be made in the n8n workflow and reflected here
