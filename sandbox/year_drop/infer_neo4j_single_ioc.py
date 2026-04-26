"""
Per-IOC attribution eval — mirrors the /attribute API's single-IOC use case.

For every Neo4j IOC that:
  (a) belongs to an event whose APT is in the paper's 22-class vocab, AND
  (b) string-matches an existing IOC node in the paper graph,
we build a temp EVENT node wired to JUST that one IOC and ask the GNN to
predict the APT. We then score top-1 APT and nation accuracy.

Ambiguous IOCs (same string seen under multiple APT labels in Neo4j) are
resolved by majority vote; ties are skipped.

Usage:
    python3 infer_neo4j_single_ioc.py --config A
    python3 infer_neo4j_single_ioc.py --config B
    python3 infer_neo4j_single_ioc.py --config C
    python3 infer_neo4j_single_ioc.py --config D
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score

TRAIL_SRC = Path(__file__).resolve().parents[2] / 'trail' / 'src'
sys.path.insert(0, str(TRAIL_SRC))

from models.gnn import SageClassifier  # noqa: E402

# Reuse maps from infer_neo4j
from infer_neo4j import (  # noqa: E402
    LABEL_MAP, APT_TO_IDX, APT_TO_NATION, NATIONS, NATION_TO_IDX,
    APT_IDX_TO_NATION_IDX, build_name_index, load_fold_model, get_fold_paths,
    DATASET,
)


def collect_ioc_labels(events):
    """Return {(type, lower_str): apt_idx} for IOCs with unambiguous APT."""
    votes = defaultdict(Counter)
    for ev in events:
        apt = ev['apt'].upper()
        if apt not in APT_TO_IDX:
            continue
        idx = APT_TO_IDX[apt]
        for d in ev.get('domains', []):
            votes[('domains', d.lower())][idx] += 1
        for ip in ev.get('ips', []):
            votes[('ips', ip.lower())][idx] += 1
        for u in ev.get('urls', []):
            votes[('urls', u.lower())][idx] += 1

    labeled = {}
    n_ambig = 0
    for k, c in votes.items():
        top = c.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            n_ambig += 1
            continue
        labeled[k] = top[0][0]
    return labeled, n_ambig


def insert_single_ioc_events(g, ioc_nids):
    """Insert one temp EVENT per IOC, each wired to just that one IOC nid."""
    csr = g.edge_csr
    type_event = g.type_dict['EVENT']
    n_new = len(ioc_nids)

    next_nid = g.x.size(0)
    last_ptr = int(csr.ptr[-1])

    new_x = torch.full((n_new,), type_event, dtype=g.x.dtype)
    new_feat = torch.full((n_new,), -1, dtype=g.feat_map.dtype)

    new_idx = torch.tensor(ioc_nids, dtype=csr.idx.dtype)
    ptrs = torch.arange(1, n_new + 1, dtype=csr.ptr.dtype) + last_ptr

    g.x = torch.cat([g.x, new_x])
    g.feat_map = torch.cat([g.feat_map, new_feat])
    csr.idx = torch.cat([csr.idx, new_idx])
    csr.ptr = torch.cat([csr.ptr, ptrs])

    return torch.arange(next_nid, next_nid + n_new, dtype=torch.long)


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', choices=['A', 'B', 'C', 'D'], required=True)
    args = ap.parse_args()

    print(f'[load] paper graph')
    g = torch.load(DATASET / 'full_graph_csr.pt', weights_only=False)
    print(f'[load] name index')
    name_idx = build_name_index(g)
    print(f'        indexed {len(name_idx):,} IOC names')

    print(f'[load] Neo4j events')
    with open(Path(__file__).parent / 'neo4j_events.json') as f:
        events = json.load(f)
    print(f'        total events={len(events)}')

    print(f'[label] collecting per-IOC labels')
    ioc_labels, n_ambig = collect_ioc_labels(events)
    print(f'        unambiguous-labeled IOCs={len(ioc_labels):,}  ambiguous-skipped={n_ambig}')

    # Resolve to paper-graph nids
    nids, true_apt, types = [], [], []
    n_unmatched = 0
    for (t, s), apt_idx in ioc_labels.items():
        nid = name_idx.get((t, s))
        if nid is None:
            n_unmatched += 1
            continue
        nids.append(nid)
        true_apt.append(apt_idx)
        types.append(t)
    print(f'        matched-to-graph IOCs={len(nids):,}  unmatched={n_unmatched}')

    if not nids:
        print('NOTHING TO PREDICT'); return

    type_counts = Counter(types)
    print(f'        by type: domains={type_counts["domains"]} '
          f'ips={type_counts["ips"]} urls={type_counts["urls"]}')

    print(f'[insert] one temp EVENT per IOC')
    temp_nids = insert_single_ioc_events(g, nids)
    true_apt = torch.tensor(true_apt, dtype=torch.long)

    print(f'[infer] running 5 fold ensemble for config {args.config}')
    paths = get_fold_paths(args.config)
    avg_softmax = None
    n_loaded = 0
    for i, p in enumerate(paths):
        if not Path(p).exists():
            print(f'  fold {i}: MISSING {p}, skipping')
            continue
        m = load_fold_model(p)
        out = m.inference(g, temp_nids)
        sm = torch.softmax(out, dim=1).cpu().numpy()
        avg_softmax = sm if avg_softmax is None else avg_softmax + sm
        n_loaded += 1
        print(f'  fold {i}: ok')
        del m
    if avg_softmax is None:
        print('NO MODELS LOADED'); return
    avg_softmax = avg_softmax / n_loaded

    pred_apt = avg_softmax.argmax(axis=1)
    true_np = true_apt.numpy()

    apt_acc = accuracy_score(true_np, pred_apt)
    apt_bacc = balanced_accuracy_score(true_np, pred_apt)
    nat_true = APT_IDX_TO_NATION_IDX[true_np]
    nat_pred = APT_IDX_TO_NATION_IDX[pred_apt]
    nat_acc = accuracy_score(nat_true, nat_pred)
    nat_bacc = balanced_accuracy_score(nat_true, nat_pred)

    # Per-type breakdown
    types_arr = np.array(types)
    print(f'\n=== Per-IOC results: config {args.config} (n={len(nids)}) ===')
    print(f'  Tier-3 APT    : acc={apt_acc:.4f}  bacc={apt_bacc:.4f}')
    print(f'  Tier-2 Nation : acc={nat_acc:.4f}  bacc={nat_bacc:.4f}')
    for t in ['domains', 'ips', 'urls']:
        m = types_arr == t
        if m.sum() == 0:
            continue
        a3 = accuracy_score(true_np[m], pred_apt[m])
        a2 = accuracy_score(nat_true[m], nat_pred[m])
        print(f'  [{t:>7s}] n={m.sum():5d}  apt-acc={a3:.4f}  nat-acc={a2:.4f}')

    # Save
    out_path = Path(__file__).parent / args.config / 'neo4j_single_ioc_predictions.npz'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             true_apt=true_np, pred_apt=pred_apt,
             softmax=avg_softmax, types=types_arr,
             ioc_nids=np.array(nids))
    print(f'  -> saved {out_path}')

    # Append metrics row
    results_path = Path(__file__).parent / 'neo4j_single_ioc_results.csv'
    row = pd.DataFrame([{
        'config': args.config, 'n': len(nids),
        'apt_acc': apt_acc, 'apt_bacc': apt_bacc,
        'nat_acc': nat_acc, 'nat_bacc': nat_bacc,
        'n_domains': int((types_arr == 'domains').sum()),
        'n_ips': int((types_arr == 'ips').sum()),
        'n_urls': int((types_arr == 'urls').sum()),
    }])
    if results_path.exists():
        existing = pd.read_csv(results_path)
        existing = existing[existing['config'] != args.config]
        row = pd.concat([existing, row], ignore_index=True)
    row.sort_values('config').to_csv(results_path, index=False)
    print(f'  -> appended to {results_path}')


if __name__ == '__main__':
    main()
