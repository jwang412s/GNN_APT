"""
Visualization utilities for clustering results

Implements PCA projection and distance heatmap visualization.
"""

import numpy as np
from typing import Optional

try:
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False
    PCA = None

from ..config import CONFIG


def _cluster_medoids(M: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """
    Extract one representative medoid per cluster for visualization
    
    Args:
        M: Distance matrix
        labels: Cluster labels
    
    Returns:
        Array of medoid indices
    """
    ids = []
    for cid in sorted(set(int(x) for x in labels if int(x) != -1)):
        idx = np.where(labels == cid)[0]
        if idx.size == 0:
            continue
        sub = M[np.ix_(idx, idx)]
        avg = sub.mean(axis=1)
        medoid_local = idx[int(np.argmin(avg))]
        ids.append(medoid_local)
    return np.array(ids, dtype=int)


def visualize_clusters_pca(
    M: np.ndarray,
    labels: np.ndarray,
    out_path: str = "clustering_pca.png",
    config: Optional[dict] = None
):
    """
    PCA visualization with automatic sampling for large datasets
    
    Args:
        M: Distance matrix
        labels: Cluster labels
        out_path: Output file path
        config: Configuration dict (defaults to CONFIG)
    """
    if not VISUALIZATION_AVAILABLE:
        print("⚠ Visualization skipped: matplotlib or sklearn not available")
        return
    
    if config is None:
        config = CONFIG
    
    if not config.get("viz", {}).get("enabled", True):
        return
    
    n = M.shape[0]
    viz = config["viz"]
    mode = viz.get("mode", "auto")
    
    if mode == "off":
        return
    elif mode == "cluster_medoids":
        plot_idx = _cluster_medoids(M, labels)
    else:
        maxn = int(viz.get("pca_sample_size", 8000))
        if n > maxn:
            rng = np.random.default_rng(config.get("seed", 1337))
            plot_idx = np.sort(rng.choice(n, size=maxn, replace=False))
        else:
            plot_idx = np.arange(n, dtype=int)
    
    if plot_idx.size == 0:
        return
    
    S = 1.0 - M[np.ix_(plot_idx, plot_idx)]
    S = np.clip(S, 0.0, 1.0)
    coords = PCA(n_components=2, random_state=config.get("seed", 1337)).fit_transform(S)
    
    fig = plt.figure(figsize=tuple(viz.get("figsize_pca", [10, 7])), dpi=int(viz.get("dpi", 200)))
    ax = fig.add_subplot(111)
    
    sub_labels = labels[plot_idx]
    uniq = sorted(set(int(x) for x in sub_labels))
    for cid in uniq:
        mask = sub_labels == cid
        if cid == -1:
            ax.scatter(coords[mask, 0], coords[mask, 1], s=6, marker="x", c="k", label="noise", alpha=0.5)
        else:
            ax.scatter(coords[mask, 0], coords[mask, 1], s=8, label=f"c{cid}", alpha=0.7)
    
    k = int(viz.get("label_top_k_clusters", 15))
    if k > 0:
        sizes = [(cid, int(np.sum(labels == cid))) for cid in uniq if cid != -1]
        sizes.sort(key=lambda x: x[1], reverse=True)
        for cid, _ in sizes[:k]:
            ii = np.where((sub_labels == cid))[0]
            if ii.size == 0:
                continue
            xy = coords[ii].mean(axis=0)
            ax.text(xy[0], xy[1], f"c{cid}", fontsize=8)
    
    ax.set_title("PCA projection of domain clusters")
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.0), fontsize=7, ncol=1)
    fig.tight_layout()
    fig.savefig(out_path, dpi=int(viz.get("dpi", 200)))
    plt.close(fig)
    print(f"✓ Saved PCA visualization to {out_path}")


def visualize_distance_heatmap(
    M: np.ndarray,
    labels: np.ndarray,
    out_path: str = "clustering_heatmap.png",
    config: Optional[dict] = None
):
    """
    Distance heatmap ordered by cluster id with size guard
    
    Args:
        M: Distance matrix
        labels: Cluster labels
        out_path: Output file path
        config: Configuration dict (defaults to CONFIG)
    """
    if not VISUALIZATION_AVAILABLE:
        print("⚠ Visualization skipped: matplotlib not available")
        return
    
    if config is None:
        config = CONFIG
    
    if not config.get("viz", {}).get("enabled", True):
        return
    
    viz = config["viz"]
    maxn = int(viz.get("heatmap_max_n", 4000))
    n = M.shape[0]
    if n > maxn:
        print(f"  Heatmap skipped: n={n} exceeds heatmap_max_n={maxn}")
        return
    
    # order by cluster id then by index, put noise last
    order = np.argsort(np.where(labels == -1, np.max(labels) + 1, labels))
    M_ord = M[np.ix_(order, order)]
    
    fig = plt.figure(figsize=tuple(viz.get("figsize_heatmap", [10, 10])), dpi=int(viz.get("dpi", 200)))
    ax = fig.add_subplot(111)
    im = ax.imshow(M_ord, interpolation="nearest", aspect="auto")
    ax.set_title("Distance heatmap ordered by cluster id")
    fig.tight_layout()
    fig.savefig(out_path, dpi=int(viz.get("dpi", 200)))
    plt.close(fig)
    print(f"✓ Saved distance heatmap to {out_path}")

