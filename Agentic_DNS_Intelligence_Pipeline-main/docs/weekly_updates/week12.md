# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 12  
**Date:** November 19 – November 25, 2025  
**Team Members:** Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi

---

## 1. Summary
This week, the team met with Shadid and presented a walkthrough of the progress across all major components of the architecture. The team demonstrated the full end-to-end processing workflow, tested live with a malicious domain provided by Shadid. The LLM-based attribution successfully identified the threat actor with a confidence of 16%, validating the pipeline end-to-end. Shadid was satisfied with the results and encouraged the team to continue refining clustering and work toward improving attribution confidence.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| End-to-end n8n workflow demo | Mohsen | Done | Live demo using mentor-provided malicious domain. |
| Clustering implementation | Zihan | In Progress | Reviewed with mentor; next: improve cluster separation and metrics. |
| Attribution testing (IOC data) | Mohammad / Mohsen | In Progress | First working attribution result using ThreatFox and AlienVault data; needs tuning. |
| Architecture status update | Entire Team | Done | Shared full progress overview with Shadid (enrichment → clustering → attribution). |

---

## 3. Key Learnings / Issues
- The full pipeline runs smoothly, validating integration between enrichment, processing, and attribution.
- LLM attribution works but needs more supporting fingerprints from clustering and IOC-based actor profiles to boost confidence.
- Shadid emphasized improving cluster quality before attempting deeper attribution logic.
- Additional actor-domain data (OTX + ThreatFox) will help stabilize attribution scores.

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Improve clustering quality (distance metrics + feature weighting) | Zihan | Dec 2 |
| Build actor-based reference clusters from IOC data (OTX + ThreatFox) | Mohammad / Zihan | Dec 3 |
| Implement similarity scoring between domain clusters and actor clusters | Mohammad / Zihan | Dec 4 |
| Improve LLM attribution prompts using enriched fingerprints | Mohsen | Dec 5 |
| Finalized automated reports (JSON → PDF/HTML) | Mohsen | Dec 6 |

---

## 5. Blockers / Help Needed
- No blockers this week.

---

## 6. Next Meeting
**Date / Time:** December 3, 2025 — 4:30 PM  
**Agenda:**
- Review clustering improvements and metrics  
- Show updated attribution confidence results  
- Present draft report-generation workflow  
- Plan final project integration steps

