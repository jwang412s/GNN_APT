# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 13  
**Date:** November 26 – December 2, 2025  
**Team Members:** Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi

---

## 1. Summary
This week, the team continued to refine the clustering and attribution pipeline. Work focused on improving domain-to-infrastructure clustering quality, building stronger actor-reference clusters from OTX and ThreatFox, and tuning the LLM prompts and evidence models to improve threat-actor identification confidence. The team is preparing to show improved cluster separation and attribution precision at the next meeting.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| Clustering refinement | Zihan | In Progress | Experimenting with distance metrics, feature weighting, and cluster validation scores. |
| Actor-reference cluster construction | Mohammad | In Progress | Merged OTX + ThreatFox actor IOCs; working on fingerprint generation. |
| Attribution confidence improvement | Mohsen | Done | Testing improved LLM prompts and enriched evidence patterns. |


---

## 3. Key Learnings / Issues
- Better cluster quality directly improves attribution confidence; feature importance tuning has measurable impact.  
- Actor-reference clusters benefit from combining multiple IOC sources rather than relying on a single feed.  
- LLM attribution improves when supplied with structured, enriched fingerprints (ASN, registrar, geo, TLS signals).  
- Some clusters remain sparse; enrichment may need fallback heuristics (e.g., fewer-feature similarity scoring).

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Finalize first stable clustering model and evaluate using silhouette/modularity | Zihan | Dec 5 |
| Complete actor-fingerprint generation & implement comparison logic | Mohammad | Dec 6 |
| Improve LLM attribution prompt with scoring justification | Mohsen | Dec 7 |
| Assemble first full automated report (actor + confidence) | Mohsen | Dec 8 |

---

## 5. Blockers / Help Needed
- None reported this week.

---

## 6. Next Meeting
**Date / Time:** December 3, 2025 — 4:30 PM  
**Agenda:**  
- Review updated clustering results  
- Demonstrate improved actor-identification confidence  
- Discuss integration into final end-to-end pipeline  
- Confirm report-generation format for final submission
