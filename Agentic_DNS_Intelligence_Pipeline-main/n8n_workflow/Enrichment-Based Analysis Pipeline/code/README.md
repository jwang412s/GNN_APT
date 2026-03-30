# Extracted Code

This directory contains JavaScript logic **extracted verbatim from n8n Code nodes** used in the enrichment-based analysis pipeline.

The files in this directory are provided **for transparency and reviewability only**.  
They do not represent a standalone codebase and are not executed independently.

## Relationship to the Workflow

- The **n8n workflow JSON** is the authoritative execution definition.
- JavaScript in this directory is derived directly from Code nodes within that workflow.
- Any changes to execution logic must be made in the n8n workflow and re-extracted if needed.

## Scope

At present, this directory includes:
- Lightweight preprocessing logic used during indicator normalization
- Report rendering and formatting logic used during output generation

No other pipeline stages implement custom JavaScript logic.

## Usage Notes

- Files are mapped one-to-one with n8n Code nodes.
- Code is copied without refactoring or modification.
- Dependencies on n8n execution context (for example, `$input`, `$json`) are expected and preserved.

## Extensibility

Additional files may be added in the future if new Code nodes are introduced.  
This directory should not be used to introduce new logic outside the workflow.

