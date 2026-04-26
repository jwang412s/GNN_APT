#!/usr/bin/env python3
"""
Chronological train/test split experiment (no hardcoded decay weighting).

Answers: "Does recency matter, without baking in a τ?"

Three runs with identical architecture and identical 70/30 per-class split
size — the ONLY thing that changes is WHICH 30% of each class is held out:

  --split forward   →  oldest 70% per class → train,  newest 30% → val
                       ("train on past, predict future")
  --split backward  →  newest 70% per class → train,  oldest 30% → val
                       ("train on future, predict past" — sanity check)
  --split random    →  random 70/30 per class (control baseline)

Interpretation:
  forward_acc  ≪  random_acc  →  recent events are genuinely harder to predict
                                 from older labeled data → recency matters;
                                 temporal drift is real.
  forward_acc  ≈  random_acc  →  event age does not meaningfully shift the
                                 decision boundary → the no-temporal win is
                                 NOT about recency, it's about feature noise.
  backward_acc >  forward_acc  →  asymmetric in time; past is easier to
                                 retrodict than future is to predict.

Per-class stratification is critical: a naive chronological split would
collapse rare classes (e.g. APT29 with n≈14) entirely into one side and
confound temporal signal with class-distribution shift.

Usage:
    python3 -u train_gnn_temporal_split.py \\
        --split forward \\
        --name tsplit_7apt_forward \\
        --apts 'Kimsuky,APT28,Mustang Panda,Turla,APT37,APT29,APT41' \\
        --zero-temporal

Then run the same command with --split backward and --split random
(changing --name each time), and compare the three training_results.json.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from trail_gnn.neo4j_client import Neo4jClient
from trail_gnn.training_hierarchical import train_pipeline_temporal_split
from trail_gnn import config


def main():
    parser = argparse.ArgumentParser(
        description=("Train TRAIL GNN on a chronological train/test split "
                     "(forward/backward/random) — no hardcoded decay τ.")
    )
    parser.add_argument("--split", required=True,
                        choices=["forward", "backward", "random"],
                        help="Per-class chronological split mode.")
    parser.add_argument("--name", type=str, default=None,
                        help=("Experiment name (results saved to "
                              "models/<name>/). Defaults to "
                              "temporal_split_<split>."))
    parser.add_argument("--train-frac", type=float, default=0.7,
                        help="Fraction of each class assigned to train (default 0.7)")
    parser.add_argument("--ae-epochs", type=int, default=config.AE_EPOCHS)
    parser.add_argument("--gnn-epochs", type=int, default=config.GNN_EPOCHS)
    parser.add_argument("--tier3-threshold", type=float, default=None,
                        help="Override config.TIER3_CONFIDENCE")
    parser.add_argument("--tier2-threshold", type=float, default=None,
                        help="Override config.TIER2_CONFIDENCE")
    parser.add_argument("--zero-temporal", action="store_true",
                        help=("Zero temporal features (matches the "
                              "hierarchical_7apt_no_temporal setup)."))
    parser.add_argument("--apts", type=str, default=None,
                        help=("Comma-separated APT subset to train on. "
                              "Example: 'Kimsuky,APT28,Mustang Panda,Turla,"
                              "APT37,APT29,APT41'"))
    args = parser.parse_args()

    if args.tier3_threshold is not None:
        config.TIER3_CONFIDENCE = args.tier3_threshold
    if args.tier2_threshold is not None:
        config.TIER2_CONFIDENCE = args.tier2_threshold

    if args.apts:
        apts = [a.strip() for a in args.apts.split(",") if a.strip()]
        config.set_apt_groups(apts)

    name = args.name or f"temporal_split_{args.split}"
    model_dir = os.path.join(config.MODEL_DIR, name)

    print(f"APT groups ({config.NUM_CLASSES}): {config.APT_GROUPS}")
    print(f"Nations  ({config.NUM_NATIONS}): {config.NATIONS}")
    print(f"Tier-3 threshold: {config.TIER3_CONFIDENCE}")
    print(f"Tier-2 threshold: {config.TIER2_CONFIDENCE}")
    print(f"Split mode:       {args.split}")
    print(f"Train fraction:   {args.train_frac}")
    print(f"Zero temporal:    {args.zero_temporal}")
    print(f"AE epochs / GNN epochs: {args.ae_epochs} / {args.gnn_epochs}")
    print(f"Output dir: {model_dir}")

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

        result = train_pipeline_temporal_split(
            split=args.split,
            client=client,
            ae_epochs=args.ae_epochs,
            gnn_epochs=args.gnn_epochs,
            model_dir=model_dir,
            train_frac=args.train_frac,
            zero_temporal=args.zero_temporal,
        )

        print(f"\n{'='*60}")
        print(f"TRAINING COMPLETE — temporal_split ({args.split})")
        print(f"{'='*60}")
        print(f"  tier-3 (named actor):    {result['tier3_accuracy']:.4f}")
        print(f"  tier-2 (nation state):   {result['tier2_accuracy']:.4f}")
        print(f"  hierarchical (routed):   {result['hierarchical_accuracy']:.4f}")
        print()
        ts = result.get("temporal_split", {})
        tr, va = ts.get("train", {}), ts.get("val", {})
        if tr and va:
            print(f"  train age (p5/med/p95 days): "
                  f"{tr.get('p05', 0):.0f} / "
                  f"{tr.get('median_age_days', 0):.0f} / "
                  f"{tr.get('p95', 0):.0f}   (n={tr.get('n', 0)})")
            print(f"  val   age (p5/med/p95 days): "
                  f"{va.get('p05', 0):.0f} / "
                  f"{va.get('median_age_days', 0):.0f} / "
                  f"{va.get('p95', 0):.0f}   (n={va.get('n', 0)})")
        print()
        print(f"  Training time: {result['training_time_seconds']:.1f}s")
        print(f"  Model saved:   {result['model_path']}")
        print()
        print("  Next: run the other two --split modes (same --apts / flags),")
        print("  then compare the three tier-3 accuracies to read off")
        print("  the recency effect without any hardcoded τ.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
