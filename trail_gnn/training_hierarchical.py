"""
Hierarchical training pipeline for TRAIL.

Same structure as trail_gnn/training.py, but the per-fold evaluator reports
three metrics instead of one:

  1. tier3_accuracy:
     Standard top-1 on named actor. Matches training.py's val_accuracy.
     A prediction is correct only if argmax == true APT.

  2. tier2_accuracy:
     Map both predicted APT and true APT through config.APT_TO_NATION, then
     compare nations. An APT37 event misclassified as Kimsuky counts as
     correct here (both North Korea) — the "tier-2 rescue" story from the
     Palo Alto Unit 42 framework.

  3. hierarchical (confidence-routed):
     Uses config.TIER3_CONFIDENCE / TIER2_CONFIDENCE to decide *which*
     tier to report per event:
       - max_softmax >= 0.45  → commit to named actor (tier 3)
       - max_softmax >= 0.30  → back off to nation state (tier 2)
       - max_softmax <  0.30  → abstain (tier 1, activity cluster only)
     Then scores each event at its assigned tier. Overall accuracy is
     correct/total with abstentions counted as incorrect, plus per-tier
     accuracy + coverage stats so the tradeoff is visible.

Everything else — vocab build, graph export, AE training, event feature
pooling, SMOTE, GraphSAGE architecture, 5-fold CV — is identical to
training.py. Reusing those functions directly.
"""

import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.model_selection import StratifiedKFold
from torch_geometric.data import HeteroData

from . import config
from .neo4j_client import Neo4jClient
from .vocabularies import VocabularySet
from .graph_export import export_graph
from .autoencoders import AutoencoderSet
from .model import TRAILHeteroGNN
from .training import _compute_event_features, _apply_smote


# ---------------------------------------------------------------------------
# Temporal decay weighting
# ---------------------------------------------------------------------------

def _fetch_event_ages(client: Neo4jClient) -> tuple[torch.Tensor, datetime, list[str]]:
    """
    Fetch pulse_created for every Event node in graph_export's ORDER BY e.id
    and return (age_days, t_ref, event_ids).

    age_days[i] = (t_ref - pulse_created[i]) in days, clamped to >= 0.
    t_ref is the max pulse_created across the graph.
    Events with missing timestamps are assigned the median age so they get a
    weight-neutral decay under any reasonable tau.
    """
    rows = client.run_query(
        "MATCH (e:Event) RETURN e.id AS id, e.pulse_created AS pulse_created "
        "ORDER BY e.id"
    )
    event_ids: list[str] = [r["id"] for r in rows]
    parsed: list[datetime | None] = []
    for r in rows:
        raw = r.get("pulse_created")
        dt: datetime | None = None
        if raw:
            s = str(raw).replace("Z", "+00:00")
            try:
                d = datetime.fromisoformat(s)
                if d.tzinfo is not None:
                    d = d.astimezone(timezone.utc).replace(tzinfo=None)
                dt = d
            except (ValueError, TypeError):
                pass
        parsed.append(dt)

    finite_dts = [d for d in parsed if d is not None]
    if not finite_dts:
        raise RuntimeError("No valid pulse_created timestamps on Event nodes")
    t_ref = max(finite_dts)

    ages = torch.full((len(rows),), float("nan"), dtype=torch.float32)
    for i, dt in enumerate(parsed):
        if dt is not None:
            ages[i] = max(0.0, (t_ref - dt).total_seconds() / 86400.0)

    finite = ages[~torch.isnan(ages)]
    median_age = float(finite.median().item())
    ages = torch.where(torch.isnan(ages), torch.tensor(median_age), ages)
    return ages, t_ref, event_ids


def _decay_weights(age_days: torch.Tensor, tau: float) -> torch.Tensor:
    """w_i = exp(-age_i / tau). tau in days."""
    return torch.exp(-age_days / float(tau))


def _decay_preflight(
    decay_w: torch.Tensor,
    age_days: torch.Tensor,
    labels: torch.Tensor,
    train_mask: torch.Tensor,
    tau: float,
) -> dict:
    """
    Print and return pre-flight stats so we can catch pathological tau choices
    before burning a 4h training run:
      - overall weight distribution
      - per-APT effective sample size Σw (flags long-tail collapse)
      - what fraction of events have w >= 0.5
    """
    labeled = train_mask
    w = decay_w[labeled]
    a = age_days[labeled]
    y = labels[labeled]

    overall = {
        "tau_days": tau,
        "n_labeled": int(labeled.sum()),
        "age_days_p05": float(np.percentile(a.numpy(), 5)),
        "age_days_median": float(a.median().item()),
        "age_days_p95": float(np.percentile(a.numpy(), 95)),
        "w_min": float(w.min().item()),
        "w_median": float(w.median().item()),
        "w_max": float(w.max().item()),
        "w_std": float(w.std().item()),
        "frac_w_ge_0.5": float((w >= 0.5).float().mean().item()),
    }

    per_apt = {}
    for idx in sorted(torch.unique(y).tolist()):
        cls_mask = y == idx
        apt = config.IDX_TO_APT.get(idx, f"class_{idx}")
        per_apt[apt] = {
            "n": int(cls_mask.sum()),
            "sum_w": round(float(w[cls_mask].sum().item()), 2),
            "mean_w": round(float(w[cls_mask].mean().item()), 4),
            "median_age": round(float(a[cls_mask].median().item()), 1),
        }

    print(f"  [decay preflight] tau={tau}d  |  "
          f"age p5/median/p95 = "
          f"{overall['age_days_p05']:.0f}/"
          f"{overall['age_days_median']:.0f}/"
          f"{overall['age_days_p95']:.0f} d  |  "
          f"w min/med/max = {overall['w_min']:.3f}/"
          f"{overall['w_median']:.3f}/{overall['w_max']:.3f}  |  "
          f"{100*overall['frac_w_ge_0.5']:.1f}% of events at w>=0.5")
    print(f"  [decay preflight] per-APT effective sample size (Σw):")
    for apt, stats in sorted(per_apt.items(),
                             key=lambda kv: -kv[1]["sum_w"]):
        print(f"    {apt:<16s} n={stats['n']:>4d}  "
              f"Σw={stats['sum_w']:>7.2f}  "
              f"median_age={stats['median_age']:>5.0f}d")

    return {"overall": overall, "per_apt": per_apt}


# ---------------------------------------------------------------------------
# Hierarchical eval primitives
# ---------------------------------------------------------------------------

_NO_NATION_SENTINEL = -1  # value stored in apt_to_nation_idx for APTs with no nation


def _build_apt_to_nation_idx() -> torch.Tensor:
    """
    Returns a LongTensor of shape [NUM_CLASSES] mapping APT index → nation
    index. APTs without nation attribution (APT_TO_NATION[apt] is None,
    e.g. Cobalt Group / Cybercrime) map to -1 and are excluded from tier-2
    and hierarchical evaluation.
    """
    mapping = torch.full((config.NUM_CLASSES,), _NO_NATION_SENTINEL, dtype=torch.long)
    for apt, idx in config.APT_TO_IDX.items():
        nation = config.APT_TO_NATION[apt]
        if nation is not None:
            mapping[idx] = config.NATION_TO_IDX[nation]
    return mapping


def _hierarchical_scores(
    logits: torch.Tensor,    # [N, NUM_CLASSES]
    true_labels: torch.Tensor,  # [N]
    apt_to_nation_idx: torch.Tensor,  # [NUM_CLASSES]
    tier3_threshold: float = config.TIER3_CONFIDENCE,
    tier2_threshold: float = config.TIER2_CONFIDENCE,
) -> dict:
    """
    Compute tier-3 / tier-2 / hierarchical-routed metrics for one fold's val set.

    Returns a dict with:
      tier3_correct, tier3_total, tier3_acc
      tier2_correct, tier2_total, tier2_acc
      hier_correct, hier_total, hier_acc
      coverage: {tier3: n, tier2: n, tier1_abstain: n}
      per_tier_accuracy: accuracy among the events actually routed to each tier
    """
    probs = F.softmax(logits, dim=-1)
    max_prob, pred_apt = probs.max(dim=-1)

    # Tier-3: plain top-1 on APT (all events in scope)
    tier3_correct = (pred_apt == true_labels).sum().item()
    tier3_total = true_labels.numel()

    # Tier-2 / hierarchical: only defined for events whose TRUE APT has a
    # nation attribution. Cobalt Group (Cybercrime) is excluded here — we
    # can't "escalate" a cybercrime prediction to a nation-state tier.
    true_nation = apt_to_nation_idx[true_labels]
    pred_nation = apt_to_nation_idx[pred_apt]
    nation_scope_mask = true_nation >= 0  # drops events whose truth is non-nation

    # Tier-2: over in-scope events, does the predicted APT share a nation
    # with the true APT? Cross-nation predictions (pred_nation == -1) auto-
    # fail — an "escalation" to Cybercrime is not a valid tier-2 answer for
    # a North Korea / Russia / China event.
    t2_mask = nation_scope_mask
    tier2_correct = int(
        ((pred_nation == true_nation) & t2_mask & (pred_nation >= 0)).sum()
    )
    tier2_total = int(t2_mask.sum())

    # Hierarchical routed: assign each event a tier based on max_prob,
    # then score at that tier. Only in-scope events (true APT has a nation)
    # are counted — out-of-scope events are excluded from the hier metric.
    routed_tier3 = max_prob >= tier3_threshold
    routed_tier2 = (max_prob >= tier2_threshold) & (~routed_tier3)
    routed_tier1 = ~(routed_tier3 | routed_tier2)

    # Tier-3 routed credit is valid for all events (even non-nation ones —
    # predicting the exact APT is always correct). Tier-2 credit requires
    # both the event and the prediction to have nation attribution.
    t3_correct_routed = (
        (pred_apt[routed_tier3] == true_labels[routed_tier3]).sum().item()
        if routed_tier3.any() else 0
    )
    t2_correct_routed = (
        (
            (pred_nation == true_nation)
            & routed_tier2
            & nation_scope_mask
            & (pred_nation >= 0)
        ).sum().item()
    )
    # tier-1 abstain: no commitment. Counts as incorrect in hier_acc but
    # is not penalized in per-tier breakdown. hier_total is the count of
    # nation-attributed events — non-nation events are out of scope.
    hier_correct = t3_correct_routed + t2_correct_routed
    hier_total = int(nation_scope_mask.sum())

    # Coverage counts reported over ALL val events (not just nation-scope)
    # so you can see how the routing policy behaves overall.
    n_t3 = int(routed_tier3.sum())
    n_t2 = int(routed_tier2.sum())
    n_t1 = int(routed_tier1.sum())
    n_excluded = int((~nation_scope_mask).sum())

    return {
        "tier3_correct": tier3_correct,
        "tier3_total": tier3_total,
        "tier3_acc": tier3_correct / tier3_total if tier3_total else 0.0,

        "tier2_correct": tier2_correct,
        "tier2_total": tier2_total,
        "tier2_acc": tier2_correct / tier2_total if tier2_total else 0.0,

        "hier_correct": hier_correct,
        "hier_total": hier_total,
        "hier_acc": hier_correct / hier_total if hier_total else 0.0,

        "coverage": {
            "tier3": n_t3, "tier2": n_t2, "tier1_abstain": n_t1,
            "non_nation_excluded_from_t2": n_excluded,
        },
        "per_tier_accuracy": {
            "tier3": (t3_correct_routed / n_t3) if n_t3 else None,
            "tier2": (t2_correct_routed / n_t2) if n_t2 else None,
        },
        "thresholds": {"tier3": tier3_threshold, "tier2": tier2_threshold},
        "per_class": _per_class_breakdown(pred_apt, true_labels),
    }


def _per_class_breakdown(pred_apt: torch.Tensor, true_labels: torch.Tensor) -> dict:
    """
    Per-APT correct/total for the current fold's val set.
    Returns {apt_idx: {"correct": int, "total": int, "apt": str, "nation": str|None}}.
    Only classes that appear in the fold's val set are included.
    """
    out = {}
    for cls in torch.unique(true_labels).tolist():
        cls_mask = true_labels == cls
        correct = int((pred_apt[cls_mask] == true_labels[cls_mask]).sum())
        total = int(cls_mask.sum())
        apt = config.IDX_TO_APT.get(cls, f"class_{cls}")
        out[int(cls)] = {
            "apt": apt,
            "nation": config.APT_TO_NATION.get(apt),
            "correct": correct,
            "total": total,
        }
    return out


# ---------------------------------------------------------------------------
# Fold trainer — identical training loop, hierarchical eval
# ---------------------------------------------------------------------------

def _train_fold_hierarchical(
    data: HeteroData,
    train_nodes: np.ndarray,
    val_nodes: np.ndarray,
    epochs: int,
    fold: int,
    apt_to_nation_idx: torch.Tensor,
    decay_w: torch.Tensor | None = None,
) -> tuple[dict, dict]:
    """
    Train one fold, return (model_state_dict, hierarchical_metrics).

    If decay_w is provided (per-event exp(-age/tau) weights), the CE loss on
    labeled training events is multiplied by decay_w in addition to
    label_confidence. Normalization uses sum(loss*w)/sum(w) so loss scale
    stays comparable to the unweighted baseline (LR doesn't effectively
    shift between runs).
    """
    num_events = data["event"].num_nodes
    fold_train_mask = torch.zeros(num_events, dtype=torch.bool)
    fold_val_mask = torch.zeros(num_events, dtype=torch.bool)
    fold_train_mask[train_nodes] = True
    fold_val_mask[val_nodes] = True

    # SMOTE (reused from training.py) — kept for result comparability with v2
    _apply_smote(
        data["event"].x, data["event"].y, fold_train_mask,
        label_confidence=data["event"].label_confidence,
    )

    metadata = data.metadata()
    model = TRAILHeteroGNN(metadata)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.GNN_LR)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        x_dict = {nt: data[nt].x for nt in data.node_types}
        out_dict = model(x_dict, data.edge_index_dict)
        logits = out_dict["event"]
        sample_weights = data["event"].label_confidence[fold_train_mask]
        if decay_w is not None:
            sample_weights = sample_weights * decay_w[fold_train_mask]
        per_sample_loss = F.cross_entropy(
            logits[fold_train_mask],
            data["event"].y[fold_train_mask],
            reduction="none",
        )
        if decay_w is not None:
            # sum-normalized weighting keeps loss magnitude comparable to
            # the baseline (sum_w != n when weights are skewed).
            w_sum = sample_weights.sum().clamp_min(1e-6)
            loss = (per_sample_loss * sample_weights).sum() / w_sum
        else:
            loss = (per_sample_loss * sample_weights).mean()
        loss.backward()
        optimizer.step()

    # Hierarchical eval
    model.eval()
    with torch.no_grad():
        x_dict = {nt: data[nt].x for nt in data.node_types}
        out_dict = model(x_dict, data.edge_index_dict)
        val_logits = out_dict["event"][fold_val_mask]
        val_labels = data["event"].y[fold_val_mask]

    metrics = _hierarchical_scores(val_logits, val_labels, apt_to_nation_idx)
    # Expose per-event val predictions so eval_by_age.py can bin by age
    # without retraining. These are val-set rows, lined up with val_nodes.
    val_probs = F.softmax(val_logits, dim=-1)
    val_max_prob, val_pred = val_probs.max(dim=-1)
    metrics["val_event_idx"] = val_nodes.tolist()
    metrics["val_true"]      = val_labels.tolist()
    metrics["val_pred"]      = val_pred.tolist()
    metrics["val_max_prob"]  = [round(float(p), 4) for p in val_max_prob.tolist()]

    cov = metrics["coverage"]
    print(
        f"  Fold {fold + 1}:  "
        f"tier3={metrics['tier3_acc']:.4f} (n={metrics['tier3_total']})  "
        f"tier2={metrics['tier2_acc']:.4f} (n={metrics['tier2_total']}; "
        f"excluded={cov['non_nation_excluded_from_t2']})  "
        f"hier={metrics['hier_acc']:.4f}  "
        f"route(t3/t2/abs)="
        f"{cov['tier3']}/{cov['tier2']}/{cov['tier1_abstain']}"
    )
    # Per-APT breakdown — one compact line per class, in config order.
    pc = metrics["per_class"]
    parts = []
    for idx in sorted(pc):
        e = pc[idx]
        t = e["total"]
        acc = e["correct"] / t if t else 0.0
        parts.append(f"{e['apt']}={e['correct']}/{t}({acc:.2f})")
    print(f"    per-APT: {' '.join(parts)}")
    return model.state_dict(), metrics


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------

def _zero_temporal_features(data: HeteroData) -> None:
    """
    Ablation: zero out the temporal feature slots in Domain / IP / URL vectors,
    in-place, BEFORE autoencoder training. This mirrors the Apr-9
    `ablation_y123_no_temporal` run and lets us isolate the lift from
    temporal features (lifespan_days, recency_days).

    Feature layouts (see feature_extraction.py):
      Domain [117]: ... | 1 active_period | 2 temporal  → last 2 dims
      IP     [509]: ... | 2 temporal                    → last 2 dims
      URL    [1517]: ... 1140 known (temporal at [1138:1140]) | 377 padding
    """
    n_domain_zeroed = n_ip_zeroed = n_url_zeroed = 0
    if data["domain"].x is not None and data["domain"].x.shape[1] >= 2:
        data["domain"].x[:, -2:] = 0.0
        n_domain_zeroed = data["domain"].x.shape[0]
    if data["ip"].x is not None and data["ip"].x.shape[1] >= 2:
        data["ip"].x[:, -2:] = 0.0
        n_ip_zeroed = data["ip"].x.shape[0]
    if data["url"].x is not None and data["url"].x.shape[1] >= 1140:
        data["url"].x[:, 1138:1140] = 0.0
        n_url_zeroed = data["url"].x.shape[0]
    print(
        f"  [ablation] Zeroing temporal features: "
        f"Domain[-2:] on {n_domain_zeroed} nodes, "
        f"IP[-2:] on {n_ip_zeroed} nodes, "
        f"URL[1138:1140] on {n_url_zeroed} nodes"
    )


def _chronological_split(
    labeled_indices: np.ndarray,
    labeled_labels: np.ndarray,
    ages_labeled: np.ndarray,
    split: str,
    train_frac: float = 0.7,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Per-class chronological train/val split.

    Within each APT class, sort labeled events by pulse_created and take:
      split='forward':  oldest train_frac → train, newest rest → val
                        (tests: does old training generalize forward in time?)
      split='backward': newest train_frac → train, oldest rest → val
                        (tests: does new training generalize backward in time?)
      split='random':   stratified random (control — no temporal structure)

    Per-class stratification keeps each APT represented in both train and val
    so per-class accuracy stays defined. Non-stratified chronological splits
    would put entire classes on one side of a time cutoff, confounding the
    temporal signal with class distribution shift.

    Returns (train_nodes, val_nodes) in graph-index space.
    """
    rng = np.random.default_rng(seed=42)
    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []

    for cls in np.unique(labeled_labels):
        cls_pos = np.where(labeled_labels == cls)[0]        # positions in labeled_*
        cls_event_idx = labeled_indices[cls_pos]            # graph event indices
        cls_ages = ages_labeled[cls_pos]
        n = len(cls_event_idx)
        if n < 2:
            # singleton class — can't split; shove into train and warn
            print(f"  [split warn] class {cls} has n={n} — all in train")
            train_parts.append(cls_event_idx)
            continue

        n_train = max(1, int(round(n * train_frac)))
        n_train = min(n_train, n - 1)  # always leave ≥1 for val

        if split == "forward":
            # oldest → train, newest → val  (oldest = largest age_days)
            order = np.argsort(-cls_ages)   # descending age (oldest first)
            train_parts.append(cls_event_idx[order[:n_train]])
            val_parts.append(cls_event_idx[order[n_train:]])
        elif split == "backward":
            # newest → train, oldest → val  (newest = smallest age_days)
            order = np.argsort(cls_ages)    # ascending age (newest first)
            train_parts.append(cls_event_idx[order[:n_train]])
            val_parts.append(cls_event_idx[order[n_train:]])
        elif split == "random":
            order = rng.permutation(n)
            train_parts.append(cls_event_idx[order[:n_train]])
            val_parts.append(cls_event_idx[order[n_train:]])
        else:
            raise ValueError(f"unknown split mode: {split!r}")

    train_nodes = np.concatenate(train_parts) if train_parts else np.array([], dtype=np.int64)
    val_nodes   = np.concatenate(val_parts)   if val_parts   else np.array([], dtype=np.int64)
    return train_nodes, val_nodes


def train_pipeline_temporal_split(
    split: str,
    client: Neo4jClient | None = None,
    ae_epochs: int = config.AE_EPOCHS,
    gnn_epochs: int = config.GNN_EPOCHS,
    model_dir: str | None = None,
    train_frac: float = 0.7,
    zero_temporal: bool = False,
) -> dict:
    """
    Single-split training for the chronological generalization experiment.

    Trains one GNN on a 70/30 per-class split chosen by `split` ∈
    {forward, backward, random}, reports hierarchical eval on the 30% val.
    No k-fold — this is a single A/B/C comparison across three runs where the
    only thing that changes is which 30% of each class is held out.

    Writes training_results.json compatible with eval_by_age.py (keeps
    val_event_idx, val_true, val_pred so the held-out slice can be
    re-analyzed later without retraining).
    """
    if split not in ("forward", "backward", "random"):
        raise ValueError(f"split must be forward|backward|random, got {split!r}")

    start_time = time.time()
    own_client = False
    if client is None:
        client = Neo4jClient()
        own_client = True

    out_dir = model_dir or os.path.join(
        config.MODEL_DIR, f"temporal_split_{split}"
    )
    os.makedirs(out_dir, exist_ok=True)

    try:
        print(f"[temporal_split] mode={split}  train_frac={train_frac}")
        print("[1/6] Building vocabularies from graph data...")
        vocabs = VocabularySet.build_from_graph(client)
        vocabs.save(path=os.path.join(out_dir, "vocabularies.json"))

        print("[2/6] Exporting graph from Neo4j...")
        data = export_graph(client, vocabs)
        print(f"  Domains: {data['domain'].x.shape[0]}, "
              f"IPs: {data['ip'].x.shape[0]}, "
              f"URLs: {data['url'].x.shape[0]}, "
              f"Events: {data['event'].num_nodes}")

        if zero_temporal:
            _zero_temporal_features(data)

        print("[3/6] Training autoencoders...")
        ae_set = AutoencoderSet()
        ae_losses = ae_set.train_all(
            data["domain"].x, data["ip"].x, data["url"].x,
            epochs=ae_epochs,
        )
        print(f"  AE losses — Domain: {ae_losses['domain']:.6f}, "
              f"IP: {ae_losses['ip']:.6f}, URL: {ae_losses['url']:.6f}")
        ae_set.save(directory=out_dir)

        print("[4/6] Encoding features with autoencoders...")
        d_enc, ip_enc, url_enc = ae_set.encode_all(
            data["domain"].x, data["ip"].x, data["url"].x,
        )
        data["domain"].x = d_enc
        data["ip"].x = ip_enc
        data["url"].x = url_enc

        print("[5/6] Computing Event node features...")
        data["event"].x = _compute_event_features(data)

        print(f"[6/6] Single {split}-chronological split, hierarchical eval...")

        # Fetch ages to drive the split
        age_days, t_ref, event_ids = _fetch_event_ages(client)
        if age_days.numel() != data["event"].num_nodes:
            raise RuntimeError(
                f"event count mismatch: ages={age_days.numel()}, "
                f"graph events={data['event'].num_nodes}"
            )

        apt_to_nation_idx = _build_apt_to_nation_idx()
        labels = data["event"].y
        train_mask = data["event"].train_mask
        labeled_indices = torch.where(train_mask)[0].numpy()
        labeled_labels = labels[train_mask].numpy()
        ages_labeled = age_days[train_mask].numpy()

        train_nodes, val_nodes = _chronological_split(
            labeled_indices, labeled_labels, ages_labeled,
            split=split, train_frac=train_frac,
        )

        # Report age stats per split side — the headline diagnostic
        def _age_stats(nodes: np.ndarray) -> dict:
            if len(nodes) == 0:
                return {"n": 0}
            a = age_days[torch.from_numpy(nodes).long()].numpy()
            return {
                "n": int(len(nodes)),
                "median_age_days": float(np.median(a)),
                "p05": float(np.percentile(a, 5)),
                "p95": float(np.percentile(a, 95)),
            }
        train_stats = _age_stats(train_nodes)
        val_stats   = _age_stats(val_nodes)
        print(f"  train: n={train_stats['n']} "
              f"age p5/med/p95 = {train_stats['p05']:.0f}/"
              f"{train_stats['median_age_days']:.0f}/"
              f"{train_stats['p95']:.0f} d")
        print(f"  val  : n={val_stats['n']} "
              f"age p5/med/p95 = {val_stats['p05']:.0f}/"
              f"{val_stats['median_age_days']:.0f}/"
              f"{val_stats['p95']:.0f} d")

        # Train one fold (fold=0 just for log label)
        model_state, metrics = _train_fold_hierarchical(
            data, train_nodes, val_nodes, gnn_epochs, fold=0,
            apt_to_nation_idx=apt_to_nation_idx,
            decay_w=None,
        )

        # Save model
        model_path = os.path.join(out_dir, "gnn_model.pt")
        torch.save(model_state, model_path)

        elapsed = time.time() - start_time
        result = {
            "status": "success",
            "experiment": f"temporal_split_{split}",
            "split_mode": split,
            "train_frac": train_frac,
            "training_time_seconds": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
            "ae_losses": ae_losses,
            "tier3_accuracy": round(metrics["tier3_acc"], 4),
            "tier2_accuracy": round(metrics["tier2_acc"], 4),
            "hierarchical_accuracy": round(metrics["hier_acc"], 4),
            "fold_details": [metrics],  # list-wrapped so eval_by_age.py works unchanged
            "thresholds": {
                "tier3": config.TIER3_CONFIDENCE,
                "tier2": config.TIER2_CONFIDENCE,
            },
            "zero_temporal": zero_temporal,
            "temporal_split": {
                "mode": split,
                "t_ref": t_ref.isoformat() if t_ref is not None else None,
                "train": train_stats,
                "val":   val_stats,
                "per_event_age_days": [round(float(a), 2) for a in age_days.tolist()],
                "event_ids_order": event_ids,
            },
            "graph_stats": {
                "domains": data["domain"].x.shape[0],
                "ips": data["ip"].x.shape[0],
                "urls": data["url"].x.shape[0],
                "events": data["event"].num_nodes,
                "labeled_events": int(train_mask.sum()),
            },
            "model_path": model_path,
        }

        log_path = os.path.join(out_dir, "training_results.json")
        try:
            with open(log_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  Training results saved to {log_path}")
        except Exception as e:
            print(f"  Warning: could not save training results: {e}")

        return result

    finally:
        if own_client:
            client.close()


def train_pipeline_hierarchical(
    client: Neo4jClient | None = None,
    k_folds: int = config.K_FOLDS,
    ae_epochs: int = config.AE_EPOCHS,
    gnn_epochs: int = config.GNN_EPOCHS,
    model_dir: str | None = None,
    zero_temporal: bool = False,
    decay_tau: float | None = None,
) -> dict:
    """
    Same pipeline as training.train_pipeline, with hierarchical eval per fold.

    Writes an extended training_results.json with tier3/tier2/hier metrics
    plus per-fold coverage stats. Best model is selected on hierarchical
    accuracy (not tier-3), so the saved artifact is tuned for the policy
    you'll actually deploy.
    """
    start_time = time.time()
    own_client = False
    if client is None:
        client = Neo4jClient()
        own_client = True

    out_dir = model_dir or os.path.join(config.MODEL_DIR, "hierarchical")
    os.makedirs(out_dir, exist_ok=True)

    try:
        # Steps 1-5: reuse exact pipeline from training.py
        print("[1/6] Building vocabularies from graph data...")
        vocabs = VocabularySet.build_from_graph(client)
        vocabs.save(path=os.path.join(out_dir, "vocabularies.json"))

        print("[2/6] Exporting graph from Neo4j...")
        data = export_graph(client, vocabs)
        print(f"  Domains: {data['domain'].x.shape[0]}, "
              f"IPs: {data['ip'].x.shape[0]}, "
              f"URLs: {data['url'].x.shape[0]}, "
              f"Events: {data['event'].num_nodes}")

        if zero_temporal:
            _zero_temporal_features(data)

        print("[3/6] Training autoencoders...")
        ae_set = AutoencoderSet()
        ae_losses = ae_set.train_all(
            data["domain"].x, data["ip"].x, data["url"].x,
            epochs=ae_epochs,
        )
        print(f"  AE losses — Domain: {ae_losses['domain']:.6f}, "
              f"IP: {ae_losses['ip']:.6f}, URL: {ae_losses['url']:.6f}")
        ae_set.save(directory=out_dir)

        print("[4/6] Encoding features with autoencoders...")
        d_enc, ip_enc, url_enc = ae_set.encode_all(
            data["domain"].x, data["ip"].x, data["url"].x,
        )
        data["domain"].x = d_enc
        data["ip"].x = ip_enc
        data["url"].x = url_enc

        print("[5/6] Computing Event node features...")
        data["event"].x = _compute_event_features(data)

        # Step 6: k-fold with hierarchical eval
        print(f"[6/6] Training {config.GNN_LAYERS}-layer GraphSAGE "
              f"({k_folds}-fold CV, hierarchical eval)...")

        apt_to_nation_idx = _build_apt_to_nation_idx()

        labels = data["event"].y
        train_mask = data["event"].train_mask
        labeled_indices = torch.where(train_mask)[0].numpy()
        labeled_labels = labels[train_mask].numpy()

        # --- Temporal decay (optional) ---
        age_days: torch.Tensor | None = None
        decay_w: torch.Tensor | None = None
        t_ref: datetime | None = None
        event_ids: list[str] = []
        decay_preflight_stats: dict | None = None
        if decay_tau is not None:
            print(f"[decay] fetching pulse_created, tau={decay_tau}d...")
            age_days, t_ref, event_ids = _fetch_event_ages(client)
            if age_days.numel() != data["event"].num_nodes:
                raise RuntimeError(
                    f"event count mismatch: ages={age_days.numel()}, "
                    f"graph events={data['event'].num_nodes} "
                    "(graph_export and _fetch_event_ages ORDER BY diverged)"
                )
            decay_w = _decay_weights(age_days, decay_tau)
            decay_preflight_stats = _decay_preflight(
                decay_w, age_days, labels, train_mask, decay_tau
            )

        fold_metrics = []
        best_hier_acc = 0.0
        best_model_state = None

        skf = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=42)
        for fold, (train_idx, val_idx) in enumerate(
            skf.split(labeled_indices, labeled_labels)
        ):
            train_nodes = labeled_indices[train_idx]
            val_nodes = labeled_indices[val_idx]

            model_state, metrics = _train_fold_hierarchical(
                data, train_nodes, val_nodes, gnn_epochs, fold,
                apt_to_nation_idx,
                decay_w=decay_w,
            )
            fold_metrics.append(metrics)

            if metrics["hier_acc"] > best_hier_acc:
                best_hier_acc = metrics["hier_acc"]
                best_model_state = model_state

        # Save best model
        model_path = os.path.join(out_dir, "gnn_model.pt")
        if best_model_state:
            torch.save(best_model_state, model_path)

        # Aggregate
        def _mean(key: str) -> float:
            return float(np.mean([m[key] for m in fold_metrics]))

        # Per-APT micro-average across folds: sum correct, sum total, divide.
        # This matches how per-APT accuracy was reported for v2 in the summary table.
        per_apt_totals: dict[int, dict] = {}
        for m in fold_metrics:
            for idx, entry in m["per_class"].items():
                slot = per_apt_totals.setdefault(
                    idx,
                    {"apt": entry["apt"], "nation": entry["nation"],
                     "correct": 0, "total": 0},
                )
                slot["correct"] += entry["correct"]
                slot["total"]   += entry["total"]
        per_apt_summary = {
            int(idx): {
                **v,
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else 0.0,
            }
            for idx, v in sorted(per_apt_totals.items())
        }

        elapsed = time.time() - start_time
        result = {
            "status": "success",
            "training_time_seconds": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
            "ae_losses": ae_losses,
            "mean_tier3_accuracy": round(_mean("tier3_acc"), 4),
            "mean_tier2_accuracy": round(_mean("tier2_acc"), 4),
            "mean_hierarchical_accuracy": round(_mean("hier_acc"), 4),
            "tier3_fold_accuracies": [round(m["tier3_acc"], 4) for m in fold_metrics],
            "tier2_fold_accuracies": [round(m["tier2_acc"], 4) for m in fold_metrics],
            "hier_fold_accuracies": [round(m["hier_acc"], 4) for m in fold_metrics],
            "fold_details": fold_metrics,
            "per_apt_summary": per_apt_summary,
            "thresholds": {
                "tier3": config.TIER3_CONFIDENCE,
                "tier2": config.TIER2_CONFIDENCE,
            },
            "zero_temporal": zero_temporal,
            "decay": {
                "tau_days": decay_tau,
                "t_ref": t_ref.isoformat() if t_ref is not None else None,
                "preflight": decay_preflight_stats,
                "per_event_age_days": (
                    [round(float(a), 2) for a in age_days.tolist()]
                    if age_days is not None else None
                ),
                "event_ids_order": event_ids if event_ids else None,
            } if decay_tau is not None else None,
            "graph_stats": {
                "domains": data["domain"].x.shape[0],
                "ips": data["ip"].x.shape[0],
                "urls": data["url"].x.shape[0],
                "events": data["event"].num_nodes,
                "labeled_events": int(train_mask.sum()),
            },
            "model_path": model_path,
        }

        log_path = os.path.join(out_dir, "training_results.json")
        try:
            with open(log_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  Training results saved to {log_path}")
        except Exception as e:
            print(f"  Warning: could not save training results: {e}")

        return result

    finally:
        if own_client:
            client.close()
