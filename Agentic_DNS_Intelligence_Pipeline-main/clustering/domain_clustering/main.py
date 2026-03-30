"""
Command-line entry point for domain clustering pipeline
"""

if __name__ == "__main__":
    import argparse
    import sys
    
    # Import from package
    sys.path.insert(0, '.')
    from domain_clustering import run_pipeline, set_config_preset, CONFIG
    
    parser = argparse.ArgumentParser(
        description="DNS-Based Threat Actor Attribution via Clustering"
    )
    parser.add_argument(
        "enriched_path",
        help="Path to enriched domain CSV/Parquet file"
    )
    parser.add_argument(
        "--labeled",
        help="Path to labeled data for evaluation (optional)",
        default=None
    )
    parser.add_argument(
        "--preset",
        choices=["baseline", "practical", "conservative"],
        default="practical",
        help="Weight preset to use"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=150,
        help="Time window in days (default: 150)"
    )
    
    args = parser.parse_args()
    
    # Set configuration
    set_config_preset(args.preset)
    CONFIG["time_window_days"] = args.window
    
    # Run pipeline
    run_pipeline(args.enriched_path, args.labeled, CONFIG)

