"""
Evaluate a trained config (A/B/C/D) on the Neo4j 2023-2026 event set.

Pipeline
--------
1. Load Neo4j events from neo4j_events.json
2. Filter to events whose APT is in the paper's 22-class label space
   (case-insensitive). This gives 1,265 of 1,740 events.
3. Resolve each event's IOCs (domain/ip/url) to existing paper-graph nids
   by string match. Drop unmatched IOCs. Drop events with 0 matched IOCs.
4. Insert each surviving event as a temporary EVENT node in the paper graph,
   wired only to matched IOCs. (Not added to g.event_ids — no label leak.)
5. For each of the 5 fold checkpoints in the config, run inference on all
   temp-event nids in one batched pass. Average softmax across folds.
6. Argmax -> APT prediction. Map APT->nation via APT_TO_NATION.
   Compute tier-3 (APT) and tier-2 (Nation) acc / balanced acc.

Usage:
    python3 infer_neo4j.py --config A
    python3 infer_neo4j.py --config B
    python3 infer_neo4j.py --config C
    python3 infer_neo4j.py --config D

For config A (baseline), pass --baseline-weights to point at the
trail/src/weights/2-layer/ checkpoints (the ones already trained).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score

TRAIL_SRC = Path(__file__).resolve().parents[2] / 'trail' / 'src'
sys.path.insert(0, str(TRAIL_SRC))

from models.gnn import SageClassifier  # noqa: E402

DATASET = TRAIL_SRC.parent / 'TKG_data' / 'otx_dataset_timestamped'

# 22-class label map (paper's). Indexed 0..21.
LABEL_MAP = {
    0: 'APT28', 1: 'TA511', 2: 'APT34', 3: 'APT35', 4: 'COBALT GROUP',
    5: 'APT38', 6: 'MOLERATS', 7: 'TA551', 8: 'APT41', 9: 'FIN11',
    10: 'GOLD WATERFALL', 11: 'FIN7', 12: 'TEAMTNT', 13: 'APT29',
    14: 'APT27', 15: 'TURLA', 16: 'KIMSUKY', 17: 'MUSTANG PANDA',
    18: 'APT37', 19: 'BLACKENERGY', 20: 'MAGECART', 21: 'MUDDYWATER',
}
APT_TO_IDX = {v.upper(): k for k, v in LABEL_MAP.items()}

APT_TO_NATION = {
    'APT28': 'Russia', 'APT29': 'Russia', 'TURLA': 'Russia', 'BLACKENERGY': 'Russia',
    'APT34': 'Iran', 'APT35': 'Iran', 'MUDDYWATER': 'Iran',
    'APT37': 'North Korea', 'APT38': 'North Korea', 'KIMSUKY': 'North Korea',
    'APT41': 'China', 'APT27': 'China', 'MUSTANG PANDA': 'China',
    'MOLERATS': 'Palestine',
    'FIN7': 'Criminal', 'FIN11': 'Criminal', 'COBALT GROUP': 'Criminal',
    'TA511': 'Criminal', 'TA551': 'Criminal', 'GOLD WATERFALL': 'Criminal',
    'MAGECART': 'Criminal', 'TEAMTNT': 'Criminal',
}
NATIONS = sorted(set(APT_TO_NATION.values()))
NATION_TO_IDX = {n: i for i, n in enumerate(NATIONS)}
APT_IDX_TO_NATION_IDX = np.array(
    [NATION_TO_IDX[APT_TO_NATION[LABEL_MAP[i]]] for i in range(22)]
)


def build_name_index(g):
    """{(type, lower_str): nid} for all IOC nodes."""
    name_idx = {}
    for ntype, fname in (("domains", "domains.csv"),
                         ("ips", "ips.csv"),
                         ("urls", "urls.csv")):
        col = pd.read_csv(DATASET / fname, sep="\t",
                          usecols=["ioc"])["ioc"].astype(str).str.lower().values
        type_id = g.type_dict[ntype]
        node_mask = (g.x == type_id).nonzero(as_tuple=True)[0]
        feat_idx = g.feat_map[node_mask].tolist()
        for nid, ridx in zip(node_mask.tolist(), feat_idx):
            if 0 <= ridx < len(col):
                name_idx.setdefault((ntype, col[ridx]), nid)
    return name_idx


def insert_temp_events(g, events, name_idx):
    """For each event, resolve IOCs to nids and insert a temp EVENT node.
    Returns (temp_nids, true_apt_idx, n_matched_iocs) lists.
    Events with 0 matched IOCs are skipped.
    Mutates g.x, g.feat_map, g.edge_csr in-place."""
    csr = g.edge_csr
    type_event = g.type_dict['EVENT']

    new_x = [g.x]
    new_feat = [g.feat_map]
    new_idx_chunks = [csr.idx]
    new_ptr_chunks = [csr.ptr]

    next_nid = g.x.size(0)
    last_ptr = int(csr.ptr[-1])

    temp_nids = []
    true_apt_idx = []
    n_matched_list = []

    for ev in events:
        # Resolve IOCs
        matched = []
        for d in ev['domains']:
            key = ('domains', d.lower())
            if key in name_idx: matched.append(name_idx[key])
        for ip in ev['ips']:
            key = ('ips', ip.lower())
            if key in name_idx: matched.append(name_idx[key])
        for u in ev['urls']:
            key = ('urls', u.lower())
            if key in name_idx: matched.append(name_idx[key])
        matched = list(dict.fromkeys(matched))  # dedupe, preserve order

        if not matched:
            continue

        # Append node
        new_x.append(torch.tensor([type_event], dtype=g.x.dtype))
        new_feat.append(torch.tensor([-1], dtype=g.feat_map.dtype))

        # Append CSR row
        nb = torch.tensor(matched, dtype=csr.idx.dtype)
        new_idx_chunks.append(nb)
        last_ptr += len(matched)
        new_ptr_chunks.append(torch.tensor([last_ptr], dtype=csr.ptr.dtype))

        temp_nids.append(next_nid)
        true_apt_idx.append(APT_TO_IDX[ev['apt'].upper()])
        n_matched_list.append(len(matched))
        next_nid += 1

    g.x = torch.cat(new_x)
    g.feat_map = torch.cat(new_feat)
    csr.idx = torch.cat(new_idx_chunks)
    csr.ptr = torch.cat(new_ptr_chunks)

    return torch.tensor(temp_nids, dtype=torch.long), \
           torch.tensor(true_apt_idx, dtype=torch.long), \
           n_matched_list


def load_fold_model(weights_path: Path):
    sd, args, kwargs = torch.load(weights_path, weights_only=False)
    sd.pop('criterion.weight', None)
    kwargs = dict(kwargs); kwargs['class_weights'] = None
    m = SageClassifier(*args, **kwargs)
    m.load_state_dict(sd)
    m.eval()
    return m


def get_fold_paths(config: str):
    """Return list of 5 checkpoint paths for the given config."""
    if config == 'A':
        # use original baseline checkpoints
        wdir = TRAIL_SRC / 'weights' / '2-layer'
        names = [
            'gnn_train-0.680_max_lprop+feats+ae-new-data.pt',
            'gnn_train-0.730_max_lprop+feats+ae-new-data.pt',
            'gnn_train-0.777_max_lprop+feats+ae-new-data.pt',
            'gnn_train-0.719_max_lprop+feats+ae-new-data.pt',
            'gnn_train-0.769_max_lprop+feats+ae-new-data.pt',
        ]
        return [wdir / n for n in names]
    wdir = Path(__file__).parent / config / 'weights'
    return [wdir / f'fold{i}.pt' for i in range(5)]


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', choices=['A','B','C','D'], required=True)
    args = ap.parse_args()

    print(f'[load] paper graph')
    g = torch.load(DATASET / 'full_graph_csr.pt', weights_only=False)
    print(f'[load] name index')
    name_idx = build_name_index(g)
    print(f'        indexed {len(name_idx):,} IOC names')

    print(f'[load] Neo4j events')
    with open(Path(__file__).parent / 'neo4j_events.json') as f:
        all_events = json.load(f)

    in_vocab = [e for e in all_events if e['apt'] and e['apt'].upper() in APT_TO_IDX]
    print(f'        total={len(all_events)}  in-vocab APT={len(in_vocab)}')

    print(f'[insert] temp events')
    temp_nids, true_apt, n_match = insert_temp_events(g, in_vocab, name_idx)
    n_kept = temp_nids.size(0)
    print(f'         kept {n_kept}/{len(in_vocab)} (had >=1 matching IOC)')
    print(f'         matched IOCs: median={int(np.median(n_match))} '
          f'p90={int(np.percentile(n_match, 90))} max={int(np.max(n_match))}')

    if n_kept == 0:
        print('NOTHING TO PREDICT'); return

    print(f'[infer] running 5 fold ensemble for config {args.config}')
    paths = get_fold_paths(args.config)
    avg_softmax = None
    for i, p in enumerate(paths):
        if not Path(p).exists():
            print(f'  fold {i}: MISSING {p}, skipping')
            continue
        m = load_fold_model(p)
        out = m.inference(g, temp_nids)
        sm = torch.softmax(out, dim=1).cpu().numpy()
        avg_softmax = sm if avg_softmax is None else avg_softmax + sm
        print(f'  fold {i}: ok')
        del m
    if avg_softmax is None:
        print('NO MODELS LOADED'); return
    avg_softmax = avg_softmax / 5.0  # 5-fold ensemble

    pred_apt = avg_softmax.argmax(axis=1)
    true_apt_np = true_apt.numpy()

    apt_acc = accuracy_score(true_apt_np, pred_apt)
    apt_bacc = balanced_accuracy_score(true_apt_np, pred_apt)

    nat_true = APT_IDX_TO_NATION_IDX[true_apt_np]
    nat_pred = APT_IDX_TO_NATION_IDX[pred_apt]
    nat_acc = accuracy_score(nat_true, nat_pred)
    nat_bacc = balanced_accuracy_score(nat_true, nat_pred)

    print(f'\n=== Results: config {args.config} on Neo4j (n={n_kept}) ===')
    print(f'  Tier-3 APT    : acc={apt_acc:.4f}  bacc={apt_bacc:.4f}')
    print(f'  Tier-2 Nation : acc={nat_acc:.4f}  bacc={nat_bacc:.4f}')

    # Save per-event predictions for downstream slicing
    out_path = Path(__file__).parent / args.config / 'neo4j_predictions.npz'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             true_apt=true_apt_np, pred_apt=pred_apt,
             softmax=avg_softmax, n_match=np.array(n_match),
             temp_nids=temp_nids.numpy())
    print(f'  -> saved {out_path}')

    # Append metrics to results table
    results_path = Path(__file__).parent / 'neo4j_eval_results.csv'
    row = pd.DataFrame([{
        'config': args.config, 'n': n_kept,
        'apt_acc': apt_acc, 'apt_bacc': apt_bacc,
        'nat_acc': nat_acc, 'nat_bacc': nat_bacc,
    }])
    if results_path.exists():
        existing = pd.read_csv(results_path)
        existing = existing[existing['config'] != args.config]  # overwrite same config
        row = pd.concat([existing, row], ignore_index=True)
    row.to_csv(results_path, index=False)


if __name__ == '__main__':
    main()
