# n8n Agentic Flow – Execution Diagram

This diagram represents the real execution flow of the Agentic-AI DNS Intelligence Pipeline
as implemented in the n8n workflow.

```mermaid
graph TD

subgraph Initialization
A(Webhook) --> B(Domain Split);
end

subgraph Parallel Enrichment
B --> C(VirusTotal);
B --> D(AlienVaultOTX);
B --> E(WhoIsFreaks);
end

subgraph Data Wrapping
D --> D1(AVOTX Data Wrapper);
E --> E1(WhoIs Data Wrapper);
end

subgraph Data Merge 
C --> F(Data Merge);
D1 --> F;
E1 --> F;
end

subgraph Schema Lock
F --> G(Data Schema Lock);
end

subgraph Enrichment Check
G --> H{If Enriched};
end

subgraph Analysis & Reporting
H -- true --> I(LLM Reasoning);
H -- false --> R(Early Webhook Response);
I --> J(Normalizing);
J --> K(HTML Generation);
K --> L(Writing to Disk);
L --> R(Final Webhook Response);
end
