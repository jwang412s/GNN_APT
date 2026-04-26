#!/usr/bin/env python3
"""
Train the TRAIL GNN with hierarchical (tiered) evaluation.

Three metrics per fold:
  - tier3_accuracy: named-actor top-1 (matches train_gnn.py)
  - tier2_accuracy: nation-state (predicted APT mapped to nation)
  - hierarchical_accuracy: confidence-routed (uses TIER3/TIER2 thresholds)

Use this when you want to reframe tier-3 failures as tier-2 successes.
"APT37 misclassified as Kimsuky" is wrong at tier-3, right at tier-2.

Usage:
    python3 -u train_gnn_hierarchical.py --name hierarchical_v1
    python3 -u train_gnn_hierarchical.py --name hier_custom \\
        --tier3-threshold 0.5 --tier2-threshold 0.25
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from trail_gnn.neo4j_client import Neo4jClient
from trail_gnn.training_hierarchical import train_pipeline_hierarchical
from trail_gnn import config


def main():
    parser = argparse.ArgumentParser(
        description="Train TRAIL GNN with hierarchical (tiered) evaluation"
    )
    parser.add_argument("--name", type=str, default="hierarchical_v1",
                        help="Experiment name (results saved to models/<name>/)")
    parser.add_argument("--folds", type=int, default=config.K_FOLDS)
    parser.add_argument("--ae-epochs", type=int, default=config.AE_EPOCHS)
    parser.add_argument("--gnn-epochs", type=int, default=config.GNN_EPOCHS)
    parser.add_argument("--tier3-threshold", type=float, default=None,
                        help="Override config.TIER3_CONFIDENCE")
    parser.add_argument("--tier2-threshold", type=float, default=None,
                        help="Override config.TIER2_CONFIDENCE")
    parser.add_argument("--zero-temporal", action="store_true",
                        help=("Ablation: zero out temporal features "
                              "(lifespan_days, recency_days) on Domain/IP/URL "
                              "before AE training. Use to compare against a "
                              "baseline that keeps temporal features."))
    parser.add_argument("--decay-tau", type=float, default=None,
                        help=("Temporal-decay experiment: weight labeled event "
                              "loss by exp(-age_days/tau). age_days computed "
                              "from Event.pulse_created vs the freshest event. "
                              "Typical value: 365. Leave unset for baseline."))
    parser.add_argument("--apts", type=str, default=None,
                        help=("Comma-separated APT subset to train on "
                              "(overrides config.APT_GROUPS). Each name must "
                              "exist in config.APT_TO_NATION. Example: "
                              "'Kimsuky,APT28,Mustang Panda,Turla,APT37,APT29'"))
    args = parser.parse_args()

    # Threshold overrides apply at config level so downstream uses them
    if args.tier3_threshold is not None:
        config.TIER3_CONFIDENCE = args.tier3_threshold
    if args.tier2_threshold is not None:
        config.TIER2_CONFIDENCE = args.tier2_threshold

    # APT subset override: rebuilds APT_TO_IDX / NUM_CLASSES / NATIONS / etc.
    # Must happen BEFORE train_pipeline_hierarchical is called.
    if args.apts:
        apts = [a.strip() for a in args.apts.split(",") if a.strip()]
        config.set_apt_groups(apts)

    model_dir = os.path.join(config.MODEL_DIR, args.name)

    print(f"APT groups ({config.NUM_CLASSES}): {config.APT_GROUPS}")
    print(f"Nations ({config.NUM_NATIONS}): {config.NATIONS}")
    print(f"Tier-3 threshold: {config.TIER3_CONFIDENCE}")
    print(f"Tier-2 threshold: {config.TIER2_CONFIDENCE}")
    print(f"Training: {args.folds}-fold CV, "
          f"AE epochs={args.ae_epochs}, GNN epochs={args.gnn_epochs}")
    print(f"Output dir: {model_dir}")
    print(f"Zero temporal features: {args.zero_temporal}")
    print(f"Decay tau (days):       {args.decay_tau if args.decay_tau else 'off (baseline)'}")

    client = Neo4jClient()
    try:
        events_per_apt = client.get_events_per_apt()
        total = 0
        print("\nEvents per target APT:")
        for apt in config.APT_GROUPS:
            count = events_per_apt.get(apt, 0)
            total += count
            nation = config.APT_TO_NATION[apt] or "— (non-nation)"
            print(f"  {apt:<16s} [{nation:<16s}] {count}")
        print(f"  Total labeled: {total}")

        result = train_pipeline_hierarchical(
            client=client,
            k_folds=args.folds,
            ae_epochs=args.ae_epochs,
            gnn_epochs=args.gnn_epochs,
            model_dir=model_dir,
            zero_temporal=args.zero_temporal,
            decay_tau=args.decay_tau,
        )

        print(f"\n{'='*60}")
        print("TRAINING COMPLETE — hierarchical evaluation")
        print(f"{'='*60}")
        print(f"  Mean tier-3 (named actor):    {result['mean_tier3_accuracy']:.4f}")
        print(f"  Mean tier-2 (nation state):   {result['mean_tier2_accuracy']:.4f}")
        print(f"  Mean hierarchical (routed):   {result['mean_hierarchical_accuracy']:.4f}")
        print()
        print(f"  Tier-3 per fold: {result['tier3_fold_accuracies']}")
        print(f"  Tier-2 per fold: {result['tier2_fold_accuracies']}")
        print(f"  Hier   per fold: {result['hier_fold_accuracies']}")
        print()
        print(f"  Training time: {result['training_time_seconds']:.1f}s")
        print(f"  Model saved:   {result['model_path']}")

        # Per-APT micro-averaged accuracy across folds
        pa = result.get("per_apt_summary", {})
        if pa:
            print()
            print("  Per-APT micro-average (across 5 folds):")
            print(f"  {'APT':<16s} {'nation':<14s} {'correct':>9s} / {'total':<6s}  acc")
            print(f"  {'-'*55}")
            # sort by descending accuracy for quick eyeballing
            rows = sorted(
                pa.values(),
                key=lambda x: (-x["accuracy"], -x["total"]),
            )
            for r in rows:
                nation = r.get("nation") or "—"
                bar = "█" * int(r["accuracy"] * 16)
                print(
                    f"  {r['apt']:<16s} {nation:<14s} "
                    f"{r['correct']:>9d} / {r['total']:<6d}  "
                    f"{r['accuracy']:.3f}  {bar}"
                )

    finally:
        client.close()


if __name__ == "__main__":
    main()
