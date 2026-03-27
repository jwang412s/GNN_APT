"""
4-layer heterogeneous GraphSAGE for APT attribution.

From TRAIL paper Section VI-D:
  - 4 SAGEConv layers with mean aggregation
  - Hidden dim: 512, output: 64 (encoding) → NUM_CLASSES
  - L2 normalization after each layer
  - Cross-entropy loss, LR 0.0001
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, to_hetero
from torch_geometric.data import HeteroData

from . import config


class HomogeneousGNN(nn.Module):
    """
    Homogeneous 4-layer GraphSAGE backbone.

    to_hetero() converts this into a heterogeneous GNN that handles
    different node and edge types automatically.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int = config.GNN_HIDDEN_DIM,
        out_channels: int = config.NUM_CLASSES,
        num_layers: int = config.GNN_LAYERS,
    ):
        super().__init__()
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()

        # First layer
        self.convs.append(SAGEConv(in_channels, hidden_channels, aggr="mean"))
        self.norms.append(nn.LayerNorm(hidden_channels))

        # Middle layers
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden_channels, hidden_channels, aggr="mean"))
            self.norms.append(nn.LayerNorm(hidden_channels))

        # Final layer → output classes
        self.convs.append(SAGEConv(hidden_channels, out_channels, aggr="mean"))

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i, conv in enumerate(self.convs[:-1]):
            x = conv(x, edge_index)
            x = self.norms[i](x)
            x = F.relu(x)
            x = F.normalize(x, p=2, dim=-1)  # L2 norm per paper

        # Last layer — no activation, no norm
        x = self.convs[-1](x, edge_index)
        return x


class TRAILHeteroGNN(nn.Module):
    """
    Heterogeneous GraphSAGE wrapper.

    Converts HomogeneousGNN to handle the TRAIL knowledge graph's
    multiple node types (event, domain, ip, url) and edge types.
    """

    def __init__(self, metadata: tuple, encoding_dim: int = config.AE_ENCODING_DIM):
        super().__init__()
        self.backbone = HomogeneousGNN(in_channels=encoding_dim)
        self.model = to_hetero(self.backbone, metadata, aggr="mean")

    def forward(self, x_dict: dict[str, torch.Tensor],
                edge_index_dict: dict[tuple, torch.Tensor]) -> dict[str, torch.Tensor]:
        return self.model(x_dict, edge_index_dict)

    def predict_events(self, x_dict: dict[str, torch.Tensor],
                       edge_index_dict: dict[tuple, torch.Tensor]) -> torch.Tensor:
        """Run forward pass and return softmax probabilities for Event nodes."""
        out = self.forward(x_dict, edge_index_dict)
        logits = out.get("event")
        if logits is None:
            raise ValueError("No 'event' node output from GNN")
        return F.softmax(logits, dim=-1)
