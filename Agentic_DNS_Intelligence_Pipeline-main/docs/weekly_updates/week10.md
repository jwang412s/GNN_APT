# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 10  
**Date:** November 5 – November 11, 2025  
**Team Members:** Amer Banaweer, Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi  

---

## 1. Summary
This week focused on incorporating Shadid's feedback into the project plan and technical work. Manual validation was added to verify the accuracy of clustering results. The LLM prompt is being refined to target SOC analyst needs, emphasizing reasoning for malicious activity and actionable recommendations. The team also prepared updated architecture diagrams showing current progress and iteration areas across the system components.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| Manual validation of clustering results | Han | In Progress | Sampling clusters and verifying domain coherence; findings to inform feature tuning. |
| LLM prompt refinement | Mohsen | In Progress | Integrated new SOC-oriented prompt; testing output relevance and reasoning quality. |
| Architecture update and iteration tracking | Entire Team | In Progress | Drafted architecture diagram with component status and iteration markers. |
| Attribution flow implementation | Mohammad / Zihan | In Progress | Continuing integration with known actor clusters using OTX and MITRE data. |
| n8n automation for enrichment → clustering → attribution → report | Amer / Mohsen | In Progress | Expanded node chain; refining API reliability and output formatting. |

---

## 3. Key Learnings / Issues
- Manual validation helps confirm cluster quality and highlights where distance metrics may need adjustment.
- The SOC-focused LLM prompt improves contextual relevance and output structure.
- Visualizing the architecture clarifies dependencies and iteration priorities across enrichment, clustering, and attribution blocks.

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Complete manual cluster validation and summarize findings | Han | Nov 14 |
| Finalize architecture diagram and annotate iteration points | Entire Team | Nov 14 |
| Implement final attribution flow and generate test reports | Mohammad / Zihan | Nov 14 |
| Review end-to-end pipeline output and document improvements | Entire Team | Nov 17 |

---

## 5. Blockers / Help Needed
- None currently. 

---

## 6. Next Meeting
**Date / Time:** November 19, 2025 — 4:30 PM  
**Agenda:**  
- Present updated architecture and component status  
- Share manual validation findings  
- Demo LLM output using refined prompt  
- Plan final integration and testing phase

