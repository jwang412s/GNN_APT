# Domain Clustering Architecture Diagram v2.0

## Complete Module Structure

```
domain_clustering/ (v2.0)
│
├── __init__.py                          # Main package exports
│   ├── run_pipeline                    # Main orchestration function
│   ├── build_incidents_from_infrastructure
│   ├── QualityEvaluator
│   ├── CONFIG
│   └── set_config_preset
│
├── main.py                             # CLI entry point
│   └── argparse interface
│
├── config/                             # Configuration Management
│   ├── __init__.py
│   │   └── exports: CONFIG, set_config_preset, get_config_signature
│   └── settings.py
│       ├── CONFIG dict (weights, thresholds, policies)
│       ├── set_config_preset(name)
│       └── get_config_signature() → str
│
├── models/                             # Data Structures
│   ├── __init__.py
│   │   └── exports: DomainRecord, Incident
│   ├── domain_record.py
│   │   ├── DomainRecord @dataclass
│   │   ├── _normalize_identifier_value()
│   │   ├── sanitize_token()
│   │   ├── normalize_date()
│   │   ├── pick_ts()
│   │   └── naive_root()
│   ├── incident.py
│   │   └── Incident @dataclass
│   └── cluster.py                      # Placeholder
│
├── metrics/                            # Distance & Similarity Metrics
│   ├── __init__.py
│   │   └── exports: lev_norm, jaccard_dist, registrar_dist, 
│   │                asn_dist, compute_pair_distance, jaccard_similarity
│   ├── distance_metrics.py
│   │   ├── lev_norm(a, b) → float
│   │   ├── jaccard_dist(A, B) → float
│   │   ├── registrar_dist(x, y) → float
│   │   ├── asn_dist(x, y) → float
│   │   └── compute_pair_distance(a, b, config) → float
│   └── similarity.py
│       └── jaccard_similarity(set_a, set_b) → float
│
├── clustering/                         # Clustering Algorithms
│   ├── __init__.py
│   │   └── exports: cluster_dbscan, cluster_hdbscan, cluster_combined
│   ├── dbscan_clustering.py
│   │   └── cluster_dbscan(M, config) → (labels, model)
│   ├── hdbscan_clustering.py
│   │   └── cluster_hdbscan(M, config) → (labels, model)
│   └── combined_clustering.py
│       └── cluster_combined(M, config, records) → (labels, quality_map, 
│                                                    source_algo_map, 
│                                                    cluster_sizes)
│       └── ⚠️ Runtime import: filter_clusters_by_quality (breaks circular dep)
│
├── quality/                            # Quality Evaluation
│   ├── __init__.py
│   │   └── exports: compute_structural_quality_map,
│   │                filter_clusters_by_structural_quality,
│   │                QualityEvaluator, filter_clusters_by_quality,
│   │                T_DISS, T_GOOD
│   ├── structural_quality.py          # ⭐ Dupont Method
│   │   ├── T_DISS = 0.2
│   │   ├── T_GOOD = 3
│   │   ├── FeatureQualityMetrics @dataclass
│   │   ├── ClusterQualityResult @dataclass
│   │   ├── compute_feature_dissimilarity(records, feature_name) → (avg_dissim, num_pairs)
│   │   ├── compute_cluster_structural_quality(records, config, cluster_id) → ClusterQualityResult
│   │   ├── compute_structural_quality_map(records, labels, M, config) → (quality_map, detailed_results)
│   │   └── filter_clusters_by_structural_quality(M, labels, records, threshold, config) → (filtered_labels, quality_map)
│   ├── quality_evaluator.py           # Orchestration
│   │   ├── filter_clusters_by_quality(M, labels, threshold, use_structural_quality, records) → (filtered_labels, quality_map)
│   │   └── QualityEvaluator class
│   └── llm_quality_scoring.py         # Phase 3 placeholder
│       └── LLMQualityScorer class (NotImplementedError)
│
├── incident/                           # Incident Grouping
│   ├── __init__.py
│   │   └── exports: compute_infrastructure_signature,
│   │                assign_infrastructure_incident_id,
│   │                build_incidents_from_infrastructure,
│   │                build_event_tag_sets
│   ├── incident_grouping.py
│   │   ├── compute_infrastructure_signature(registrar_id, asn) → str
│   │   ├── assign_infrastructure_incident_id(registrar_id, asn, config) → str
│   │   └── build_incidents_from_infrastructure(records, final_labels) → Dict[incident_id, metadata]
│   └── pattern_extraction.py
│       └── build_event_tag_sets(final_labels, records) → Dict[incident_id, Set[cluster_id]]
│
├── processing/                         # Data Processing
│   ├── __init__.py
│   │   └── exports: load_data, apply_time_window, ensure_event_fields,
│   │                sanitize_record, build_distance_matrix
│   ├── data_loader.py
│   │   ├── load_data(path) → DataFrame
│   │   ├── apply_time_window(df, days) → DataFrame
│   │   ├── ensure_event_fields(df, config) → DataFrame
│   │   ├── build_incident_id(row, policy, ts_utc, config) → str
│   │   └── sanitize_record(row, config) → DomainRecord
│   ├── distance_matrix.py
│   │   └── build_distance_matrix(records, config) → np.ndarray
│   └── output_handler.py              # Placeholder
│
├── pipeline/                           # Pipeline Orchestration
│   ├── __init__.py
│   │   └── exports: run_pipeline, recommend_top_k, evaluate_recommender,
│   │                visualize_clusters_pca, visualize_distance_heatmap,
│   │                build_enrichment_report, suggest_preset_from_enrichment
│   ├── clustering_pipeline.py         # ⭐ Main orchestration
│   │   └── run_pipeline(enriched_path, labeled_path, config) → None
│   │       ├── Step 1: Load & preprocess data
│   │       ├── Step 2: Build distance matrix
│   │       ├── Step 3: Run combined clustering (with records parameter)
│   │       ├── Step 4: Build infrastructure-based incidents
│   │       ├── Step 5: Save clustering results
│   │       ├── Step 6: Generate visualizations
│   │       ├── Step 7: Evaluation (if labeled data)
│   │       └── Step 8: Generate summary report
│   ├── evaluation.py
│   │   ├── recommend_top_k(query_incident_id, event_tags, k, quality_map, 
│   │                       source_algo_map, cluster_sizes) → DataFrame
│   │   └── evaluate_recommender(event_tags_query, event_tags_labeled, gt_map,
│   │                            k, quality_map, source_algo_map, cluster_sizes) → Dict
│   ├── visualization.py
│   │   ├── visualize_clusters_pca(M, labels, out_path, config) → None
│   │   └── visualize_distance_heatmap(M, labels, out_path, config) → None
│   ├── enrichment_report.py
│   │   ├── build_enrichment_report(df_norm, config) → dict
│   │   └── suggest_preset_from_enrichment(rep) → None
│   └── n8n_interface.py               # Phase 3 placeholder
│       ├── ClusteringAPI class (NotImplementedError)
│       ├── IncidentAPI class (NotImplementedError)
│       └── QualityAPI class (NotImplementedError)
│
├── attribution/                        # Attribution (Phase 3 placeholder)
│   └── __init__.py                    # Empty (recommendation in pipeline.evaluation)
│
└── utils/                              # Utility Functions
    ├── __init__.py
    │   └── exports: sanitize_token, normalize_date, pick_ts, 
│   │                naive_root, build_incident_id
    └── helpers.py
        ├── sanitize_token(s) → str
        ├── normalize_date(val) → Optional[Timestamp]
        ├── pick_ts(row, policy) → Timestamp
        ├── naive_root(domain) → str
        └── build_incident_id(row, policy, ts_utc, config) → str
```

---

## Dependency Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Entry Points                             │
│  - main.py (CLI)                                                 │
│  - domain_clustering.__init__.py (Programmatic)                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Pipeline Layer                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ clustering_pipeline.py (run_pipeline)                   │   │
│  │  ├─> processing.load_data                               │   │
│  │  ├─> processing.build_distance_matrix                   │   │
│  │  ├─> clustering.cluster_combined (with records)        │   │
│  │  ├─> incident.build_incidents_from_infrastructure      │   │
│  │  ├─> pipeline.evaluation.recommend_top_k               │   │
│  │  ├─> pipeline.visualization.visualize_clusters_pca     │   │
│  │  └─> pipeline.enrichment_report.build_enrichment_report│   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ evaluation.py, visualization.py, enrichment_report.py   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Processing & Clustering Layer                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ processing/                                              │   │
│  │  ├─> data_loader: load_data, sanitize_record           │   │
│  │  └─> distance_matrix: build_distance_matrix            │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ clustering/                                              │   │
│  │  ├─> dbscan_clustering: cluster_dbscan                 │   │
│  │  ├─> hdbscan_clustering: cluster_hdbscan               │   │
│  │  └─> combined_clustering: cluster_combined             │   │
│  │      └─> ⚠️ Runtime import: quality.filter_clusters_by_quality │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Quality & Incident Layer                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ quality/                                                 │   │
│  │  ├─> structural_quality: Dupont method               │   │
│  │  │    ├─> compute_feature_dissimilarity                │   │
│  │  │    ├─> compute_cluster_structural_quality           │   │
│  │  │    └─> filter_clusters_by_structural_quality        │   │
│  │  └─> quality_evaluator: filter_clusters_by_quality     │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ incident/                                                │   │
│  │  ├─> incident_grouping: infrastructure-based grouping  │   │
│  │  └─> pattern_extraction: build_event_tag_sets          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         Core Layer                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ config/                                                  │   │
│  │  └─> settings: CONFIG, set_config_preset               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ models/                                                  │   │
│  │  ├─> domain_record: DomainRecord @dataclass            │   │
│  │  └─> incident: Incident @dataclass                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ metrics/                                                 │   │
│  │  ├─> distance_metrics: lev_norm, jaccard_dist, etc.    │   │
│  │  └─> similarity: jaccard_similarity                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ utils/                                                   │   │
│  │  └─> helpers: sanitize_token, normalize_date, etc.     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
[Input: enriched_domains_hq.csv]
        ↓
┌─────────────────────────────────────┐
│ Step 1: Data Loading                │
│  - load_data()                      │
│  - ensure_event_fields()            │
│  - apply_time_window()              │
│  - sanitize_record() → DomainRecord[]│
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│ Step 2: Distance Matrix             │
│  - build_distance_matrix()          │
│    └─> compute_pair_distance()      │
│        ├─> lev_norm()               │
│        ├─> jaccard_dist()           │
│        ├─> registrar_dist()         │
│        └─> asn_dist()               │
│  Output: M (n×n distance matrix)    │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│ Step 3: Combined Clustering         │
│  - cluster_combined(M, config, records)│
│    ├─> cluster_dbscan(M, config)    │
│    ├─> filter_clusters_by_quality(..., records)│
│    │   └─> compute_structural_quality_map()│
│    │       └─> Dupont method      │
│    ├─> cluster_hdbscan(M, config)   │
│    └─> filter_clusters_by_quality(..., records)│
│  Output: final_labels, quality_map, │
│          source_algo_map, cluster_sizes│
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│ Step 4: Incident Grouping           │
│  - build_incidents_from_infrastructure(records, labels)│
│    ├─> assign_infrastructure_incident_id()│
│    │   └─> compute_infrastructure_signature()│
│    └─> Group by (registrar_id, asn)│
│  Output: incidents Dict             │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│ Step 5-8: Output Generation         │
│  - Save CSV/JSON files              │
│  - Generate visualizations          │
│  - Generate summary report          │
└─────────────────────────────────────┘
        ↓
[Output: clustering_output/]
```

---

## Module Dependency Graph (Simplified)

```
pipeline/
  ├─> processing/ (data_loader, distance_matrix)
  ├─> clustering/ (cluster_combined)
  │     └─> quality/ (runtime import in combined_clustering)
  ├─> incident/ (build_incidents_from_infrastructure)
  ├─> quality/ (QualityEvaluator)
  ├─> config/ (CONFIG)
  └─> pipeline/ (evaluation, visualization, enrichment_report)

clustering/
  ├─> config/ (CONFIG)
  ├─> metrics/ (distance functions)
  └─> quality/ (runtime import: filter_clusters_by_quality)

quality/
  ├─> models/ (DomainRecord)
  └─> metrics/ (lev_norm, jaccard_dist, registrar_dist, asn_dist)

incident/
  └─> models/ (DomainRecord)

processing/
  ├─> models/ (DomainRecord)
  ├─> config/ (CONFIG)
  ├─> incident/ (assign_infrastructure_incident_id)
  └─> utils/ (helpers)

metrics/
  └─> models/ (DomainRecord)

utils/
  ├─> models/ (DomainRecord)
  └─> incident/ (assign_infrastructure_incident_id)
```

---

## Key Features Highlight

### ⭐ Structural Quality (Dupont Method)
- **Location**: `quality/structural_quality.py`
- **Thresholds**: `T_DISS = 0.2`, `T_GOOD = 3`
- **Process**: Per-feature average dissimilarity → Overall quality score

### ⭐ Infrastructure-Based Incident Grouping
- **Location**: `incident/incident_grouping.py`
- **Strategy**: Group by `(registrar_id, asn)` signature
- **Output**: `infra_{signature}` incident IDs

### ⭐ Combined Clustering Strategy
- **Location**: `clustering/combined_clustering.py`
- **Strategy**: DBSCAN (precision) → HDBSCAN (recall)
- **Quality Filtering**: Structural Quality thresholds (0.4 DBSCAN, 0.2 HDBSCAN)

### ⚠️ Circular Dependency Prevention
- **Pattern**: Runtime import in `combined_clustering.py`
- **Function**: `filter_clusters_by_quality` imported inside `cluster_combined()`
- **Reason**: Breaks potential cycle `clustering` → `quality` → `clustering`

---

## Phase 3 Extension Points

1. **LLM Quality Scoring**: `quality/llm_quality_scoring.py`
2. **LLM Incident Analysis**: `incident/incident_analyzer.py` (to be created)
3. **n8n REST API**: `pipeline/n8n_interface.py`
4. **LLM Parameter Optimization**: `optimization/llm_parameter_optimizer.py` (to be created)

---

## File Statistics

- **Total Modules**: 19+ Python files
- **Packages**: 11 (`config`, `models`, `metrics`, `clustering`, `quality`, `incident`, `attribution`, `processing`, `pipeline`, `utils`, `tests`)
- **Entry Points**: 2 (`main.py`, `__init__.py`)
- **Test Scripts**: 6 (`test_01_imports.py` through `test_06_end_to_end.py`)

---

**Version**: 2.0  
**Last Updated**: 2025-11-16  
**Status**: Phase 2 Complete - All modules implemented and tested

