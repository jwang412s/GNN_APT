# 🗓 Weekly Project Update

**Project Title:** Agentic AI for DNS-Based Threat Intelligence  
**Week #:** 8  
**Date:** October 22–28, 2025  
**Team Members:** Amer Banaweer, Mohammad Badr, Mohsen Babanejad, Zihan Zhang  
**Mentor / Instructor:** Shadid Chowdhury / Dr. Mohammad Tayebi  

---

## 1. Summary
This week, the team prepared for to deliver the enrichment demo, showcasing how n8n automates domain enrichment across multiple data sources.  
Focus has also shifted toward implementing the clustering phase, starting with feature extraction and graph construction using data from the enrichment dossiers.  

---

## 2. Progress

| Task | Assigned To | Status | Notes |
|------|--------------|--------|-------|
| Build enrichment engine | Amer | Done | Demo completed successfully; n8n workflow stable. |
| Test engine | Entire Team | Done | Verified output correctness and API reliability. |
| Clustering algorithm research and node setup | Mohsen / Han | In Progress | Evaluating Louvain vs. HDBSCAN for domain grouping. |
| Graph builder and feature extraction | Mohammad / Amer | In Progress | Working on schema linking domains, IPs, and ASNs. |
| Actor characteristics planning | Entire Team | To Do | Will begin once clusters are formed. |

---

## 3. Key Learnings / Issues
- n8n workflows can reliably handle sequential enrichment with error recovery.  
- Graph-based clustering better represents relationships between domains and infrastructure.  
- Need to define thresholds for “same cluster” linkage (e.g., ASN, registrar, TLS overlap).  
- Some APIs still have occasional rate limits; caching will be critical for clustering scale-up.  

---

## 4. Next Steps

| Action Item | Owner | Due Date |
|--------------|--------|-----------|
| Implement clustering workflow and test small dataset | Entire Team | Oct 31 |
| Compare Louvain and HDBSCAN clustering results | Amer / Mohsen | Nov 2 |
| Prepare slides for Initial Results Presentation | Mohammad | Nov 3 |
| Define attributes for actor profiling post-clustering | Mohammad / Zihan | Nov 4 |

---

## 5. Blockers / Help Needed
- None for this week.  

---

## 6. Next Meeting
**Date / Time:** October 30, 2025 — 4:30 PM  
**Agenda:**  
- Review clustering implementation progress  
- Discuss preliminary results and metrics (modularity, silhouette)  
- Outline actor-characteristics extraction plan  
- Prepare final slides for Initial Results Presentation  
