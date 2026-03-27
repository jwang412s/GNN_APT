"""
Full TRAIL training pipeline.

Steps (from paper Section VI):
  1. Export graph from Neo4j → HeteroData
  2. Build vocabularies from graph data
  3. Train 3 autoencoders (Domain/IP/URL → 64-dim)
  4. Replace raw features with AE encodings
  5. Set Event node features via mean-pooling of connected IOC encodings
  6. Train 4-layer heterogeneous GraphSAGE with SMOTE + stratified 5-fold CV
  7. Save all model artifacts
"""

import json
import os
import time
from datetime import datetime

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


def _compute_event_features(data: HeteroData) -> torch.Tensor:
    """
    Compute Event node features by mean-pooling connected IOC encodings.

    For each event, average the 64-dim encoded features of all IOC nodes
    it is connected to via InReport edges.
    """
    num_events = data["event"].num_nodes
    encoding_dim = config.AE_ENCODING_DIM
    event_feats = torch.zeros((num_events, encoding_dim), dtype=torch.float32)
    counts = torch.zeros(num_events, dtype=torch.float32)

    for edge_type in data.edge_types:
        src_type, rel, dst_type = edge_type
        if src_type == "event" and "in_report" in rel:
            ei = data[edge_type].edge_index
            dst_x = data[dst_type].x
            if dst_x is None or dst_x.shape[0] == 0:
                continue
            for col in range(ei.shape[1]):
                ev_idx = ei[0, col].item()
                ioc_idx = ei[1, col].item()
                if ioc_idx < dst_x.shape[0]:
                    event_feats[ev_idx] += dst_x[ioc_idx]
                    counts[ev_idx] += 1

    # Mean pool (avoid divide by zero)
    mask = counts > 0
    event_feats[mask] = event_feats[mask] / counts[mask].unsqueeze(1)

    return event_feats


def _apply_smote(
    features: torch.Tensor, labels: torch.Tensor,
    mask: torch.Tensor, label_confidence: torch.Tensor | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Apply SMOTE oversampling to balance class distribution.
    Only operates on labeled (masked) nodes.

    Returns (features, labels, confidence_weights) — synthetic events
    inherit the mean label_confidence of their source class.
    """
    orig_conf = label_confidence[mask] if label_confidence is not None else torch.ones(mask.sum())

    try:
        from imblearn.over_sampling import SMOTE
    except ImportError:
        print("Warning: imbalanced-learn not installed, skipping SMOTE")
        return features[mask], labels[mask], orig_conf

    X = features[mask].numpy()
    y = labels[mask].numpy()

    # Need at least 2 classes and enough samples per class
    unique, counts = np.unique(y, return_counts=True)
    if len(unique) < 2:
        return features[mask], labels[mask], orig_conf

    # Set k_neighbors to min(5, min_class_count - 1)
    min_count = counts.min()
    k = min(5, max(1, min_count - 1))

    # Compute per-class mean confidence before SMOTE
    class_mean_conf = {}
    for cls in unique:
        cls_mask = (labels[mask] == cls)
        class_mean_conf[cls] = orig_conf[cls_mask].mean().item()

    try:
        smote = SMOTE(k_neighbors=k, random_state=42)
        X_res, y_res = smote.fit_resample(X, y)

        # Build confidence weights: original events keep their confidence,
        # synthetic events inherit their class's mean confidence
        n_original = X.shape[0]
        conf_res = np.zeros(len(y_res), dtype=np.float32)
        conf_res[:n_original] = orig_conf.numpy()
        for i in range(n_original, len(y_res)):
            conf_res[i] = class_mean_conf.get(y_res[i], 0.1)

        return (
            torch.from_numpy(X_res).float(),
            torch.from_numpy(y_res).long(),
            torch.from_numpy(conf_res).float(),
        )
    except Exception as e:
        print(f"SMOTE failed ({e}), using original data")
        return features[mask], labels[mask], orig_conf


def train_pipeline(
    client: Neo4jClient | None = None,
    k_folds: int = config.K_FOLDS,
    ae_epochs: int = config.AE_EPOCHS,
    gnn_epochs: int = config.GNN_EPOCHS,
) -> dict:
    """
    Run the full TRAIL training pipeline.

    Returns a dict with training metrics and model paths.
    """
    start_time = time.time()
    own_client = False
    if client is None:
        client = Neo4jClient()
        own_client = True

    try:
        # ----- Step 1: Build vocabularies -----
        print("[1/6] Building vocabularies from graph data...")
        vocabs = VocabularySet.build_from_graph(client)
        vocabs.save()

        # ----- Step 2: Export graph -----
        print("[2/6] Exporting graph from Neo4j...")
        data = export_graph(client, vocabs)
        print(f"  Domains: {data['domain'].x.shape[0]}, "
              f"IPs: {data['ip'].x.shape[0]}, "
              f"URLs: {data['url'].x.shape[0]}, "
              f"Events: {data['event'].num_nodes}")

        # ----- Step 3: Train autoencoders -----
        print("[3/6] Training autoencoders...")
        ae_set = AutoencoderSet()
        ae_losses = ae_set.train_all(
            data["domain"].x, data["ip"].x, data["url"].x,
            epochs=ae_epochs
        )
        print(f"  AE losses — Domain: {ae_losses['domain']:.6f}, "
              f"IP: {ae_losses['ip']:.6f}, URL: {ae_losses['url']:.6f}")
        ae_set.save()

        # ----- Step 4: Replace features with AE encodings -----
        print("[4/6] Encoding features with autoencoders...")
        d_enc, ip_enc, url_enc = ae_set.encode_all(
            data["domain"].x, data["ip"].x, data["url"].x
        )
        data["domain"].x = d_enc
        data["ip"].x = ip_enc
        data["url"].x = url_enc

        # ----- Step 5: Compute Event features -----
        print("[5/6] Computing Event node features...")
        event_feats = _compute_event_features(data)
        data["event"].x = event_feats

        # ----- Step 6: Train GNN with stratified k-fold -----
        print(f"[6/6] Training {config.GNN_LAYERS}-layer GraphSAGE "
              f"({k_folds}-fold CV)...")

        labels = data["event"].y
        train_mask = data["event"].train_mask
        labeled_indices = torch.where(train_mask)[0].numpy()
        labeled_labels = labels[train_mask].numpy()

        if len(labeled_indices) < k_folds:
            print(f"  Only {len(labeled_indices)} labeled events, "
                  f"training on all (no CV)")
            best_model_state = _train_single_fold(
                data, labeled_indices, labeled_indices, gnn_epochs
            )
            fold_accuracies = []
        else:
            skf = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=42)
            fold_accuracies = []
            best_acc = 0.0
            best_model_state = None

            for fold, (train_idx, val_idx) in enumerate(
                skf.split(labeled_indices, labeled_labels)
            ):
                train_nodes = labeled_indices[train_idx]
                val_nodes = labeled_indices[val_idx]

                model_state, val_acc = _train_fold(
                    data, train_nodes, val_nodes, gnn_epochs, fold
                )
                fold_accuracies.append(val_acc)

                if val_acc > best_acc:
                    best_acc = val_acc
                    best_model_state = model_state

        # Save best model
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        model_path = os.path.join(config.MODEL_DIR, "gnn_model.pt")
        if best_model_state:
            torch.save(best_model_state, model_path)

        elapsed = time.time() - start_time
        result = {
            "status": "success",
            "training_time_seconds": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
            "ae_losses": ae_losses,
            "fold_accuracies": fold_accuracies,
            "mean_accuracy": round(float(np.mean(fold_accuracies)), 4) if fold_accuracies else None,
            "graph_stats": {
                "domains": data["domain"].x.shape[0],
                "ips": data["ip"].x.shape[0],
                "urls": data["url"].x.shape[0],
                "events": data["event"].num_nodes,
                "labeled_events": int(train_mask.sum()),
            },
            "model_path": model_path,
        }

        # Save training results to disk
        log_path = os.path.join(config.MODEL_DIR, "training_results.json")
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


def _train_fold(
    data: HeteroData,
    train_nodes: np.ndarray,
    val_nodes: np.ndarray,
    epochs: int,
    fold: int,
) -> tuple[dict, float]:
    """Train one fold, return (model_state_dict, val_accuracy)."""
    # Build train/val masks for this fold
    num_events = data["event"].num_nodes
    fold_train_mask = torch.zeros(num_events, dtype=torch.bool)
    fold_val_mask = torch.zeros(num_events, dtype=torch.bool)
    fold_train_mask[train_nodes] = True
    fold_val_mask[val_nodes] = True

    # SMOTE on training features — synthetic events inherit class mean confidence
    train_x, train_y, train_conf = _apply_smote(
        data["event"].x, data["event"].y, fold_train_mask,
        label_confidence=data["event"].label_confidence,
    )

    # Create model
    metadata = data.metadata()
    model = TRAILHeteroGNN(metadata)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.GNN_LR)

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        x_dict = {nt: data[nt].x for nt in data.node_types}
        out_dict = model(x_dict, data.edge_index_dict)

        logits = out_dict["event"]
        # Per-sample weighting using DST label_confidence
        # Uses confidence from graph (not SMOTE) since logits are per-node
        sample_weights = data["event"].label_confidence[fold_train_mask]
        per_sample_loss = F.cross_entropy(
            logits[fold_train_mask],
            data["event"].y[fold_train_mask],
            reduction="none",
        )
        loss = (per_sample_loss * sample_weights).mean()
        loss.backward()
        optimizer.step()

    # Validate
    model.eval()
    with torch.no_grad():
        x_dict = {nt: data[nt].x for nt in data.node_types}
        out_dict = model(x_dict, data.edge_index_dict)
        logits = out_dict["event"]
        preds = logits[fold_val_mask].argmax(dim=-1)
        correct = (preds == data["event"].y[fold_val_mask]).sum().item()
        total = fold_val_mask.sum().item()
        val_acc = correct / total if total > 0 else 0.0

    # Per-class validation breakdown
    val_labels = data["event"].y[fold_val_mask].numpy()
    val_preds = preds.numpy()
    unique_classes = np.unique(val_labels)
    class_report = {}
    for cls in unique_classes:
        cls_mask = val_labels == cls
        cls_correct = (val_preds[cls_mask] == val_labels[cls_mask]).sum()
        cls_total = cls_mask.sum()
        class_report[int(cls)] = {"correct": int(cls_correct), "total": int(cls_total)}

    print(f"  Fold {fold + 1}: val_accuracy = {val_acc:.4f} "
          f"(correct={correct}/{total}, classes={class_report})")
    return model.state_dict(), val_acc


def _train_single_fold(
    data: HeteroData,
    train_nodes: np.ndarray,
    val_nodes: np.ndarray,
    epochs: int,
) -> dict:
    """Train on all labeled data (no validation split)."""
    num_events = data["event"].num_nodes
    mask = torch.zeros(num_events, dtype=torch.bool)
    mask[train_nodes] = True

    metadata = data.metadata()
    model = TRAILHeteroGNN(metadata)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.GNN_LR)

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        x_dict = {nt: data[nt].x for nt in data.node_types}
        out_dict = model(x_dict, data.edge_index_dict)
        logits = out_dict["event"]
        sample_weights = data["event"].label_confidence[mask]
        per_sample_loss = F.cross_entropy(
            logits[mask], data["event"].y[mask], reduction="none"
        )
        loss = (per_sample_loss * sample_weights).mean()
        loss.backward()
        optimizer.step()

    return model.state_dict()
