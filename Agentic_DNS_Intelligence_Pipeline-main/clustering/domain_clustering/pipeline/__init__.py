"""
Pipeline utilities for clustering and evaluation

This package contains modules for:
- Evaluation metrics and recommendation
- Visualization of clustering results
- Enrichment quality reporting
- Main pipeline orchestration
"""

from .clustering_pipeline import run_pipeline
from .evaluation import recommend_top_k, evaluate_recommender
from .visualization import visualize_clusters_pca, visualize_distance_heatmap
from .enrichment_report import build_enrichment_report, suggest_preset_from_enrichment

__all__ = [
    "run_pipeline",
    "recommend_top_k",
    "evaluate_recommender",
    "visualize_clusters_pca",
    "visualize_distance_heatmap",
    "build_enrichment_report",
    "suggest_preset_from_enrichment"
]

