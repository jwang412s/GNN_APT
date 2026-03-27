"""
Autoencoders for dimensionality reduction of heterogeneous node features.

From TRAIL paper Section VI-C:
  Encoder: Linear(d_in → 512) → ReLU → Linear(512 → 64)
  Decoder: Linear(64 → 512) → ReLU → Linear(512 → d_in)
  Loss: MSE reconstruction
"""

import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from . import config


class IOCAutoencoder(nn.Module):
    """Autoencoder that compresses high-dim IOC features to 64-dim."""

    def __init__(self, input_dim: int, hidden_dim: int = config.AE_HIDDEN_DIM,
                 encoding_dim: int = config.AE_ENCODING_DIM):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, encoding_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(encoding_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return encoded, decoded

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.encoder(x)


def train_autoencoder(
    ae: IOCAutoencoder,
    features: torch.Tensor,
    epochs: int = config.AE_EPOCHS,
    lr: float = config.AE_LR,
    batch_size: int = config.AE_BATCH_SIZE,
) -> float:
    """
    Train an autoencoder on a feature matrix.
    Returns final reconstruction loss.
    """
    if features.shape[0] == 0:
        return 0.0

    dataset = TensorDataset(features)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(ae.parameters(), lr=lr)
    criterion = nn.MSELoss()

    ae.train()
    final_loss = 0.0
    for epoch in range(epochs):
        epoch_loss = 0.0
        for (batch,) in loader:
            optimizer.zero_grad()
            _, decoded = ae(batch)
            loss = criterion(decoded, batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * batch.shape[0]
        final_loss = epoch_loss / features.shape[0]

    return final_loss


class AutoencoderSet:
    """Container for the three IOC-type autoencoders."""

    def __init__(self):
        self.domain_ae = IOCAutoencoder(config.DOMAIN_FEATURE_DIM)
        self.ip_ae = IOCAutoencoder(config.IP_FEATURE_DIM)
        self.url_ae = IOCAutoencoder(config.URL_FEATURE_DIM)

    def train_all(self, domain_x: torch.Tensor, ip_x: torch.Tensor,
                  url_x: torch.Tensor, epochs: int = config.AE_EPOCHS) -> dict:
        """Train all three autoencoders. Returns per-type reconstruction loss."""
        losses = {}
        losses["domain"] = train_autoencoder(self.domain_ae, domain_x, epochs=epochs)
        losses["ip"] = train_autoencoder(self.ip_ae, ip_x, epochs=epochs)
        losses["url"] = train_autoencoder(self.url_ae, url_x, epochs=epochs)
        return losses

    def encode_all(self, domain_x: torch.Tensor, ip_x: torch.Tensor,
                   url_x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Encode all node types to 64-dim representations."""
        self.domain_ae.eval()
        self.ip_ae.eval()
        self.url_ae.eval()

        d_enc = self.domain_ae.encode(domain_x) if domain_x.shape[0] > 0 else torch.zeros((0, config.AE_ENCODING_DIM))
        ip_enc = self.ip_ae.encode(ip_x) if ip_x.shape[0] > 0 else torch.zeros((0, config.AE_ENCODING_DIM))
        url_enc = self.url_ae.encode(url_x) if url_x.shape[0] > 0 else torch.zeros((0, config.AE_ENCODING_DIM))

        return d_enc, ip_enc, url_enc

    def save(self, directory: str = config.MODEL_DIR):
        os.makedirs(directory, exist_ok=True)
        torch.save(self.domain_ae.state_dict(), os.path.join(directory, "ae_domain.pt"))
        torch.save(self.ip_ae.state_dict(), os.path.join(directory, "ae_ip.pt"))
        torch.save(self.url_ae.state_dict(), os.path.join(directory, "ae_url.pt"))

    def load(self, directory: str = config.MODEL_DIR):
        self.domain_ae.load_state_dict(torch.load(os.path.join(directory, "ae_domain.pt"), weights_only=True))
        self.ip_ae.load_state_dict(torch.load(os.path.join(directory, "ae_ip.pt"), weights_only=True))
        self.url_ae.load_state_dict(torch.load(os.path.join(directory, "ae_url.pt"), weights_only=True))
