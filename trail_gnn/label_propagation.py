"""
Label Propagation on the TRAIL knowledge graph.

From TRAIL paper Section V:
  F_n = D^(-1/2) * A * D^(-1/2) * F_{n-1}
  4 iterations, then softmax → class probabilities.

Operates on the full heterogeneous graph by building a homogeneous
adjacency over Event nodes via their shared infrastructure.
"""

import torch
import numpy as np
from torch_geometric.data import HeteroData

from . import config


def build_event_adjacency(data: HeteroData) -> torch.Tensor:
    """
    Build a symmetric adjacency matrix over Event nodes.

    Two events are connected if they share at least one IOC node
    (domain, IP, or URL) via InReport edges.

    Returns a sparse float tensor of shape (num_events, num_events).
    """
    num_events = data["event"].num_nodes
    if num_events == 0:
        return torch.zeros((0, 0))

    # Collect event→IOC mappings from all InReport edge types
    event_to_iocs: dict[int, set[str]] = {i: set() for i in range(num_events)}

    for edge_type in data.edge_types:
        src_type, rel, dst_type = edge_type
        if src_type == "event" and "in_report" in rel:
            ei = data[edge_type].edge_index
            for col in range(ei.shape[1]):
                ev_idx = ei[0, col].item()
                ioc_idx = ei[1, col].item()
                # Use a unique key combining dst_type + index
                event_to_iocs[ev_idx].add(f"{dst_type}_{ioc_idx}")

    # Build adjacency: events sharing IOCs
    rows, cols = [], []
    event_list = list(range(num_events))
    for i in range(num_events):
        for j in range(i + 1, num_events):
            if event_to_iocs[i] & event_to_iocs[j]:  # intersection
                rows.extend([i, j])
                cols.extend([j, i])

    if not rows:
        return torch.eye(num_events)

    indices = torch.tensor([rows, cols], dtype=torch.long)
    values = torch.ones(len(rows), dtype=torch.float32)
    adj = torch.sparse_coo_tensor(indices, values, (num_events, num_events))

    # Add self-loops
    self_loops = torch.arange(num_events, dtype=torch.long)
    self_idx = torch.stack([self_loops, self_loops])
    self_vals = torch.ones(num_events, dtype=torch.float32)
    adj = adj + torch.sparse_coo_tensor(self_idx, self_vals, (num_events, num_events))
    adj = adj.coalesce()

    return adj


def symmetric_normalize(adj: torch.Tensor) -> torch.Tensor:
    """Compute D^(-1/2) * A * D^(-1/2) normalization."""
    adj_dense = adj.to_dense() if adj.is_sparse else adj
    degree = adj_dense.sum(dim=1)
    d_inv_sqrt = torch.where(
        degree > 0,
        1.0 / torch.sqrt(degree),
        torch.zeros_like(degree)
    )
    D_inv_sqrt = torch.diag(d_inv_sqrt)
    return D_inv_sqrt @ adj_dense @ D_inv_sqrt


def label_propagation(
    data: HeteroData,
    iterations: int = config.LP_ITERATIONS,
    num_classes: int = config.NUM_CLASSES,
    adj: torch.Tensor | None = None,
) -> torch.Tensor:
    """
    Run label propagation over Event nodes.

    Args:
        data: HeteroData with event labels in data["event"].y
        iterations: Number of LP iterations (default: 4)
        num_classes: Number of APT classes
        adj: Pre-computed adjacency. Built from graph if None.

    Returns:
        Tensor of shape (num_events, num_classes) with class probabilities.
    """
    num_events = data["event"].num_nodes
    if num_events == 0:
        return torch.zeros((0, num_classes))

    labels = data["event"].y
    train_mask = data["event"].train_mask

    # Initialize label matrix F
    F = torch.zeros((num_events, num_classes), dtype=torch.float32)
    for i in range(num_events):
        if train_mask[i] and labels[i] >= 0:
            F[i, labels[i]] = 1.0

    # Build or use adjacency
    if adj is None:
        adj = build_event_adjacency(data)

    # Symmetric normalization
    A_norm = symmetric_normalize(adj)

    # Iterate: F_n = A_norm @ F_{n-1}, then clamp known labels
    for _ in range(iterations):
        F = A_norm @ F
        # Re-clamp known labels
        for i in range(num_events):
            if train_mask[i] and labels[i] >= 0:
                F[i] = 0.0
                F[i, labels[i]] = 1.0

    # Softmax for final probabilities
    F = torch.softmax(F, dim=-1)

    return F


def lp_predict(
    data: HeteroData,
    iterations: int = config.LP_ITERATIONS,
) -> list[dict]:
    """
    Run LP and return predictions for unlabeled events.

    Returns list of dicts: [{event_idx, predicted_apt, confidence, probabilities}, ...]
    """
    probs = label_propagation(data, iterations=iterations)
    labels = data["event"].y
    train_mask = data["event"].train_mask

    results = []
    for i in range(probs.shape[0]):
        if not train_mask[i] or labels[i] < 0:
            conf, pred_idx = probs[i].max(dim=0)
            apt_name = config.IDX_TO_APT.get(pred_idx.item(), "Unknown")
            results.append({
                "event_idx": i,
                "predicted_apt": apt_name,
                "confidence": round(conf.item(), 4),
                "probabilities": {
                    config.IDX_TO_APT[j]: round(probs[i, j].item(), 4)
                    for j in range(probs.shape[1])
                },
            })

    return results
