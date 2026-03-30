# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 6  
**Date:** October 8-14, 2025  
**Team Members:** Amer Banaweer, Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi

---

## 1. Summary
This week the team finalized finding sources and completed the first working prototype of the **agentic enrichment workflow** in n8n.  
Enrichment sources (RDAP, crt.sh, BGPView, MaxMind GeoLite2, and OTX) were integrated and tested, and sample dossiers were generated for demo.

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| **100 – Enrichment with different fingerprints** | Entire Team | In Progress | Defined full enrichment set and integrated APIs. |
| 101 – Define the fingerprints of the domain | Mohsen | Done | Final spec drafted; aligning field names with `sources.yaml`. |
| 102 – Find sources | Mohammad | Done | Implemented and documented in `README_Task102_MVP.md`. |
| 103 – Build enrichment engine | Amer/Mohsen | Done | n8n workflow prototype running (Webhook → VirusTotal → Ollama). |
| 104 – Test engine | Han/Mohsen | In Progress | Test cases planned for next iteration. |
| **200 – Building agentic workflow (initial version)** | Entire Team | In progress | Initial agentic orchestration completed in n8n. |
| 201 – Provide agentic workflow breakdown | Mohsen/Mohammad | In Progress | Diagram and step breakdown drafted for slides. |
| 202 – Review results and provide feedback | Han | To Do | Scheduled after workflow test. |

---

## 3. Key Learnings / Issues
- Learned how to chain enrichment APIs and automate using n8n workflows.  
- OTX returns 500 errors for large domains; retry logic added.  
- MaxMind GeoLite2 provides only partial geo data — fallback to country-level granularity.  
- `.env` files must stay local and not be shared in repo.  

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Finalize fingerprint schema and update `sources.yaml` | [Member Name] | Oct 20 |
| Implement caching + TTL layer for enrichment engine | [Member Name] | Oct 20 |
| Create basic pytest scripts for enrichment validation | [Member Name] | Oct 22 |
| Prepare short demo video of the n8n workflow | Team | Oct 23 |

---

## 5. Blockers / Help Needed
- None for this week.  

---

## 6. Next Meeting
**Date / Time:** October 22, 2025 — 4:30 PM  
**Agenda:**  
- Review enrichment engine progress  
- Confirm final fingerprint schema  
- Discuss LLM labeling flow integration  
- Plan deliverables for Initial Results Presentation  
