"""
Year-drop / random-drop ablation training.

Configs:
  A: baseline (no drop)        — already trained, use existing checkpoints
  B: drop year=2018 events     — 111 events lost (~2.5% of training labels)
  C: drop year in {2018,2019}  — 970 events lost (~22%)
  D: drop 970 random events    — same volume as C, no temporal pattern (control)

"Drop" = remove from g.event_ids / g.y / g.sources so they contribute no
label supervision. The events stay in the graph as nodes with their CSR
edges intact, so message-passing topology is unchanged. Only the label
one-hot in get_features() loses them (handled cleanly because get_features
only adds one-hot for nids that appear in g.event_ids).

Outputs to sandbox/year_drop/{config}/{weights,predictions}/fold{i}.pt and
summary.txt. Checkpoint format matches train_gnn.main: (sd, args, kwargs).
"""
import argparse
import math
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import StratifiedKFold

# Make trail/src importable
TRAIL_SRC = Path(__file__).resolve().parents[2] / 'trail' / 'src'
sys.path.insert(0, str(TRAIL_SRC))

from models.gnn import SageClassifier  # noqa: E402
from train_gnn import train, get_final_preds, to_onehot  # noqa: E402

DATASET = str(TRAIL_SRC.parent / 'TKG_data' / 'otx_dataset_timestamped')
OUT_ROOT = Path(__file__).resolve().parent


def compute_drop_mask(g, ts_df: pd.DataFrame, config: str, seed: int = 42) -> torch.Tensor:
    """Return bool mask over event positions (length = g.event_ids.size(0))."""
    n = g.event_ids.size(0)
    if config == 'A':
        return torch.zeros(n, dtype=torch.bool)
    ts_df = ts_df.sort_values('event_idx').reset_index(drop=True)
    assert len(ts_df) == n, f'event_timestamp_map rows ({len(ts_df)}) != events ({n})'
    years = pd.to_datetime(ts_df['created'], errors='coerce').dt.year.fillna(-1).astype(int).values
    if config == 'B':
        return torch.from_numpy(years == 2018)
    if config == 'C':
        return torch.from_numpy(np.isin(years, [2018, 2019]))
    if config == 'D':
        rng = np.random.default_rng(seed)
        n_drop = 970  # match C
        drop_idx = rng.choice(n, size=n_drop, replace=False)
        m = np.zeros(n, dtype=bool)
        m[drop_idx] = True
        return torch.from_numpy(m)
    raise ValueError(config)


def split_after_drop(g, folds: int = 5):
    """Mirrors train_gnn.get_and_split but with the (already-shrunk) g.
    Returns generator of (tr, va, te) tuples (no graph — caller passes the
    masked g separately)."""
    kf = StratifiedKFold(n_splits=folds)
    kf_val = StratifiedKFold(n_splits=2)
    valid_mask = (g.sources == g.src_map['OTX']).logical_and(g.y != -1)
    valid_ids = g.event_ids[valid_mask]
    valid_ys = g.y[valid_mask]
    for tr, te in kf.split(valid_ids, valid_ys):
        va_, te_ = next(kf_val.split(te, valid_ys[te]))
        va = te[va_]; te2 = te[te_]
        yield (
            (valid_ids[tr], valid_ys[tr]),
            (valid_ids[va], valid_ys[va]),
            (valid_ids[te2], valid_ys[te2]),
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', choices=['A', 'B', 'C', 'D'], required=True)
    ap.add_argument('--start-fold', type=int, default=0)
    ap.add_argument('--end-fold', type=int, default=4)
    args = ap.parse_args()

    out_dir = OUT_ROOT / args.config
    (out_dir / 'weights').mkdir(parents=True, exist_ok=True)
    (out_dir / 'predictions').mkdir(parents=True, exist_ok=True)

    hp = SimpleNamespace(
        ioc_enc=64, hidden=512, layers=2, aggr='max',
        autoencoder=True, variational=False, lr=1e-4, wd=1e-5, epochs=100,
        bs=16, patience=10, sample_size=32, heads=0,
        dataset=DATASET, start_fold=args.start_fold, end_fold=args.end_fold,
    )

    g = torch.load(f'{DATASET}/full_graph_csr.pt', weights_only=False)
    ts_df = pd.read_csv(f'{DATASET}/event_timestamp_map.csv')

    drop_mask = compute_drop_mask(g, ts_df, args.config)
    keep = ~drop_mask
    n_before = g.event_ids.size(0)
    g.event_ids = g.event_ids[keep]
    g.y = g.y[keep]
    g.sources = g.sources[keep]
    n_after = g.event_ids.size(0)
    n_drop = int(drop_mask.sum())
    print(f'[{args.config}] events before={n_before} after={n_after} dropped={n_drop}')

    stats = []
    for fold, (tr, va, te) in enumerate(split_after_drop(g)):
        if fold < args.start_fold or fold > args.end_fold:
            continue
        print(f'\n=== [{args.config}] Fold {fold} ===')

        # class weights from this fold's train labels
        y_oh = to_onehot(tr[1])
        per_class = y_oh.sum(dim=0)
        weight = tr[1].size(0) - per_class

        out_dim = (g.y.max() + 1).item()
        model = SageClassifier(
            DATASET, hp.ioc_enc, hp.hidden, out_dim,
            class_weights=weight, layers=hp.layers, aggr=hp.aggr,
            autoencoder=hp.autoencoder, sample_size=hp.sample_size,
            variational=hp.variational, heads=hp.heads,
        )

        best, _ = train(hp, model, g, *tr, *va, *te)
        sd = best.pop('sd')
        torch.save((sd, model.args, model.kwargs), out_dir / 'weights' / f'fold{fold}.pt')

        model.load_state_dict(sd)
        model.eval()
        preds, ys = get_final_preds(model, g, *te)
        torch.save((preds, ys), out_dir / 'predictions' / f'fold{fold}.pt')

        best['fold'] = fold
        stats.append(best)
        # Append running summary so a long run can be inspected mid-flight
        with open(out_dir / 'progress.txt', 'a') as f:
            f.write(f"fold={fold} e={best['e']} va={best['va']:.4f} "
                    f"te-acc={best['te-acc']:.4f} te-bacc={best['te-bacc']:.4f}\n")

    df = pd.DataFrame(stats)
    print(df)
    with open(out_dir / 'summary.txt', 'w') as f:
        f.write(f'config={args.config} dropped={n_drop} kept={n_after}\n\n')
        df.to_csv(f); f.write('\n')
        df.mean(numeric_only=True).to_csv(f); f.write('\n')


if __name__ == '__main__':
    main()
