"""
DNS-Based Threat Intelligence Clustering and Attribution

Phase 2: Modularized architecture with Dupont Structural Quality
"""

from .pipeline.clustering_pipeline import run_pipeline
from .incident.incident_grouping import build_incidents_from_infrastructure
from .quality.quality_evaluator import QualityEvaluator
from .config import CONFIG, set_config_preset

__version__ = "2.0"

__all__ = [
    "run_pipeline",
    "build_incidents_from_infrastructure",
    "QualityEvaluator",
    "CONFIG",
    "set_config_preset"
]

