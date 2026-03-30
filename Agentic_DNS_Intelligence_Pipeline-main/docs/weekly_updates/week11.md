# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 11  
**Date:** November 12 – November 18, 2025  
**Team Members:** Amer Banaweer, Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi

---

## 1. Summary
This week, the team completed a milestone in the clustering phase by generating the fully enriched and structured cluster output.  
The team also performed a successful LLM-based attribution test using the domain ikmtrust.com and IOC data extracted from OTX, demonstrating how known-actor fingerprints can drive attribution.

The **Conceptual Architecture** slide was updated to show:  
✔ Enrichment done  
✔ Initial report generation done  
➡ Clustering in progress  
➡ Attribution in progress  

Work has now shifted toward defining the **report-generation workflow** and integrating it into n8n.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Clustering output generation | Han | Done | Produced `incidents_detailed.json` (nodes, infra fields, cluster IDs, quality metrics). |
| Attribution test with LLM | Mohsen | Done | Tested attribution for *ikmtrust.com* using OTX IOC data + model reasoning. |
| Architecture update | Entire Team | Done | Updated Conceptual Architecture slide for next week’s review. |
| Actor–IOC extraction (ThreatFox) | Mohammad | In Progress | Actor → domain pairs validated for clustering of known actors. |
| Initial report generation design & implementation | Mohsen | Done | Drafting structure + n8n integration plan. |

---

## 3. Key Learnings / Issues
- Cluster JSON output now provides a stable base for attribution work.  
- OTX IOC extraction yields enough historically tagged domains to build actor clusters.  
- LLM attribution produced consistent, explainable evaluations when fed enriched fingerprints.  
- Some data sources still rate-limit heavily; caching or local mirrors will be needed later.

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Implement attribution using actor clusters + distance scoring | Mohammad / Zihan | Nov 22 |
| Integrate and test enhanced cluster code into pipeline | Han / Mohsen | Nov 24 |
| Validate clustering vs. actor clusters (manual checks, precision/recall) | Han | Nov 28 |
| Prepare slides for next project review | Entire Team | Nov 29 |

---

## 5. Blockers / Help Needed
- None for this week.

---

## 6. Next Meeting
**Date / Time:** November 19, 2025 — 4:30 PM  
**Agenda:**  
- Demo LLM attribution test
- Share architecture progress status
- Finalize report-generation step  
- Confirm deliverables for final presentation
