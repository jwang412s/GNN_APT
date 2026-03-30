# Pipeline Nodes

This directory documents the **logical stages** of the enrichment-based DNS intelligence pipeline.

Each file represents a **conceptual pipeline node**, describing the analytical responsibility and data flow of that stage rather than its tool-specific implementation.

The documented nodes are intentionally defined at a higher abstraction level than the underlying n8n workflow. Multiple n8n nodes (for example, HTTP requests, control-flow nodes, or lightweight preprocessing logic) may contribute to a single documented stage.

## Scope and Intent

The purpose of this directory is to explain:
- What each stage of the pipeline is responsible for
- How data progresses through the pipeline conceptually
- How analytical responsibilities are separated

This documentation does **not** attempt to mirror n8n nodes one-to-one and should not be interpreted as an implementation specification.

## Relationship to Implementation

- The **n8n workflow JSON** is the authoritative execution definition.
- Some stages include limited JavaScript logic implemented via n8n Code nodes (for example, normalization and report rendering).
- Other stages rely on orchestration logic, external intelligence services, and native n8n functionality rather than custom code.

## Node Ordering

The files are numbered to reflect the logical execution order of the pipeline:

1. Indicator Ingestion  
2. Enrichment  
3. Threat Intelligence Correlation  
4. Contextual Reasoning  
5. Report Synthesis  

This ordering represents the conceptual flow of analysis and is stable across pipeline derivations.

## Extensibility

The node definitions are designed to support alternative or complementary analytical approaches (such as clustering-driven analysis) without requiring changes to the documented structure.

Additional pipeline derivations may reuse, extend, or reinterpret these nodes as needed.
