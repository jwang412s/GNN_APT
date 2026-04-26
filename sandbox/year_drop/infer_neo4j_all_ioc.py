"""
Per-IOC eval over ALL unambiguously-labeled IOCs from in-vocab APT events,
including the 33k that don't string-match any paper-graph node.

Unmatched IOCs are injected as new graph nodes with feat_map=-1
(zero IOC features, just the node-type one-hot — same path the model
follows at inference for an unknown IOC). Each IOC gets a single-IOC
temp EVENT wired to it.

Usage:
    python3 infer_neo4j_all_ioc.py --config A
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score

TRAIL_SRC = Path(__file__).resolve().parents[2] / 'trail' / 'src'
sys.path.insert(0, str(TRAIL_SRC))

from infer_neo4j import (  # noqa: E402
    APT_TO_IDX, APT_IDX_TO_NATION_IDX,
    build_name_index, load_fold_model, get_fold_paths, DATASET,
)
from infer_neo4j_single_ioc import collect_ioc_labels  # noqa: E402


def insert_all_iocs(g, ioc_specs, name_idx):
    """ioc_specs = list of (type, lower_str, apt_idx).
    Adds: (a) any unmatched IOC as a new graph node with feat_map=-1,
          (b) one temp EVENT per IOC wired to that single IOC nid.
    Returns (temp_event_nids, true_apt, types, was_matched)."""
    csr = g.edge_csr
    type_event = g.type_dict['EVENT']
    type_codes = {t: g.type_dict[t] for t in ('domains', 'ips', 'urls')}

    # Stage 1: assign nids to every IOC (existing or new)
    next_nid = g.x.size(0)
    new_x_chunks = []
    new_feat_chunks = []
    ioc_nids = []
    types = []
    true_apt = []
    was_matched = []

    for t, s, apt_idx in ioc_specs:
        existing = name_idx.get((t, s))
        if existing is not None:
            ioc_nids.append(existing)
            was_matched.append(True)
        else:
            ioc_nids.append(next_nid)
            new_x_chunks.append(type_codes[t])
            new_feat_chunks.append(-1)
            next_nid += 1
            was_matched.append(False)
        types.append(t)
        true_apt.append(apt_idx)

    if new_x_chunks:
        g.x = torch.cat([g.x,
                         torch.tensor(new_x_chunks, dtype=g.x.dtype)])
        g.feat_map = torch.cat([g.feat_map,
                                torch.tensor(new_feat_chunks, dtype=g.feat_map.dtype)])
        # Extend csr.ptr so new IOC nodes have empty neighbor rows
        last_ptr_now = int(csr.ptr[-1])
        pad = torch.full((len(new_x_chunks),), last_ptr_now, dtype=csr.ptr.dtype)
        csr.ptr = torch.cat([csr.ptr, pad])

    # Stage 2: append a temp EVENT row per IOC
    n_ev = len(ioc_nids)
    last_ptr = int(csr.ptr[-1])
    new_ev_x = torch.full((n_ev,), type_event, dtype=g.x.dtype)
    new_ev_feat = torch.full((n_ev,), -1, dtype=g.feat_map.dtype)
    new_idx = torch.tensor(ioc_nids, dtype=csr.idx.dtype)
    ptrs = torch.arange(1, n_ev + 1, dtype=csr.ptr.dtype) + last_ptr

    ev_start = g.x.size(0)
    g.x = torch.cat([g.x, new_ev_x])
    g.feat_map = torch.cat([g.feat_map, new_ev_feat])
    csr.idx = torch.cat([csr.idx, new_idx])
    csr.ptr = torch.cat([csr.ptr, ptrs])

    temp_nids = torch.arange(ev_start, ev_start + n_ev, dtype=torch.long)
    return (temp_nids,
            torch.tensor(true_apt, dtype=torch.long),
            np.array(types),
            np.array(was_matched))


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', choices=['A', 'B', 'C', 'D'], required=True)
    ap.add_argument('--batch', type=int, default=4096)
    args = ap.parse_args()

    print(f'[load] paper graph')
    g = torch.load(DATASET / 'full_graph_csr.pt', weights_only=False)
    print(f'[load] name index')
    name_idx = build_name_index(g)

    print(f'[load] Neo4j events')
    with open(Path(__file__).parent / 'neo4j_events.json') as f:
        events = json.load(f)
    ioc_labels, n_ambig = collect_ioc_labels(events)
    print(f'        unambig labeled IOCs={len(ioc_labels):,}  ambig-skipped={n_ambig}')

    ioc_specs = [(t, s, apt_idx) for (t, s), apt_idx in ioc_labels.items()]
    print(f'[insert] adding IOCs + temp events to graph')
    temp_nids, true_apt, types_arr, matched_arr = insert_all_iocs(g, ioc_specs, name_idx)
    n_total = temp_nids.size(0)
    n_match = int(matched_arr.sum())
    print(f'         total IOCs={n_total}  matched={n_match}  unmatched={n_total-n_match}')

    print(f'[infer] running 5-fold ensemble for config {args.config}')
    paths = get_fold_paths(args.config)
    avg_softmax = None
    n_loaded = 0
    for i, p in enumerate(paths):
        if not Path(p).exists():
            print(f'  fold {i}: MISSING {p}'); continue
        m = load_fold_model(p)
        # batched inference to keep memory sane
        sm_chunks = []
        for start in range(0, n_total, args.batch):
            chunk = temp_nids[start:start + args.batch]
            out = m.inference(g, chunk)
            sm_chunks.append(torch.softmax(out, dim=1).cpu().numpy())
        sm = np.concatenate(sm_chunks, axis=0)
        avg_softmax = sm if avg_softmax is None else avg_softmax + sm
        n_loaded += 1
        print(f'  fold {i}: ok')
        del m
    if avg_softmax is None:
        print('NO MODELS'); return
    avg_softmax = avg_softmax / n_loaded

    pred_apt = avg_softmax.argmax(axis=1)
    true_np = true_apt.numpy()
    nat_true = APT_IDX_TO_NATION_IDX[true_np]
    nat_pred = APT_IDX_TO_NATION_IDX[pred_apt]

    def metrics(mask=None):
        m = slice(None) if mask is None else mask
        return dict(
            n=int(np.asarray(mask).sum()) if mask is not None else len(true_np),
            apt_acc=accuracy_score(true_np[m], pred_apt[m]),
            apt_bacc=balanced_accuracy_score(true_np[m], pred_apt[m]),
            nat_acc=accuracy_score(nat_true[m], nat_pred[m]),
            nat_bacc=balanced_accuracy_score(nat_true[m], nat_pred[m]),
        )

    overall = metrics()
    matched = metrics(matched_arr)
    unmatched = metrics(~matched_arr)

    print(f'\n=== ALL-IOC results: config {args.config} (n={n_total}) ===')
    for label, r in [('OVERALL', overall), ('MATCHED', matched), ('UNMATCHED', unmatched)]:
        print(f'  [{label:>9s}] n={r["n"]:6d}  '
              f'apt acc={r["apt_acc"]:.4f}  bacc={r["apt_bacc"]:.4f}  | '
              f'nat acc={r["nat_acc"]:.4f}  bacc={r["nat_bacc"]:.4f}')

    # Per-type within unmatched
    print(f'  [unmatched by type]:')
    for t in ['domains', 'ips', 'urls']:
        tm = (~matched_arr) & (types_arr == t)
        if tm.sum() == 0: continue
        a3 = accuracy_score(true_np[tm], pred_apt[tm])
        a2 = accuracy_score(nat_true[tm], nat_pred[tm])
        print(f'    {t:>7s}  n={tm.sum():6d}  apt={a3:.4f}  nat={a2:.4f}')

    # Save
    out_path = Path(__file__).parent / args.config / 'neo4j_all_ioc_predictions.npz'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             true_apt=true_np, pred_apt=pred_apt,
             softmax=avg_softmax, types=types_arr, matched=matched_arr)

    results_path = Path(__file__).parent / 'neo4j_all_ioc_results.csv'
    rows = []
    for label, r in [('overall', overall), ('matched', matched), ('unmatched', unmatched)]:
        rows.append({'config': args.config, 'subset': label, **r})
    df_new = pd.DataFrame(rows)
    if results_path.exists():
        existing = pd.read_csv(results_path)
        existing = existing[existing['config'] != args.config]
        df_new = pd.concat([existing, df_new], ignore_index=True)
    df_new.sort_values(['config', 'subset']).to_csv(results_path, index=False)
    print(f'  -> {out_path}')
    print(f'  -> {results_path}')


if __name__ == '__main__':
    main()
