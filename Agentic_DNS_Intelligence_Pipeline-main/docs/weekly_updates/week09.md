# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 9  
**Date:** October 29 – November 4, 2025  
**Team Members:** Amer Banaweer, Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi  

---

## 1. Summary
This week, the team implemented the clustering approach described in the reference paper and refined the feature set for graph-based analysis.  
The group also defined a two-layer attribution model; one for new domains and another for known actor clusters (seeded from IOC sources like OTX).  
Work has begun on reviewing the automation pipeline in n8n to connect enrichment, clustering, attribution, and report generation.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| Implement paper-based clustering approach | Han | Done | Completed prototype; clusters generated from enriched dataset. |
| Attribution model design (dual-layer clustering) | Mohammad / Zihan | In Progress | Defined actor vs. domain cluster logic; integrating OTX IOC pulls. |
| End-to-end automation review (n8n) | Amer / Mohsen | In Progress | Mapped nodes for enrichment → clustering → attribution → report. |
| Report generation via n8n | TBD | To Do | Will build JSON → summary report flow next. |

---

## 3. Key Learnings / Issues
- The clustering approach from the paper worked well for infrastructure-based grouping (ASN + org + registrar).  
- Dual-layer clustering helps align new domains with known actor infrastructure for attribution.  
- OTX IOC queries vary in completeness; combining with MITRE actor references improves coverage.  
- Automation across multiple nodes requires better error handling and caching for API stability.  

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Implement attribution flow for known actor clusters | Mohammad / Zihan | Nov 7 |
| Finalize n8n automation and report output | Entire Team | Nov 12 |
| Evaluate clustering quality using silhouette + modularity metrics | Amer / Han | Nov 9 |
| Start integrating LLM-based reasoning for low-confidence attribution | Entire Team | Nov 10 |

---

## 5. Blockers / Help Needed
- No blockers for this week. 

---

## 6. Next Meeting
**Date / Time:** November 5, 2025 — 4:30 PM  
**Agenda:**  
- Demo enrichment and clustering  
- Review attribution approach + automation flow in n8n  

