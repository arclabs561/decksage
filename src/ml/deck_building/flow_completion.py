#!/usr/bin/env python3
"""
Flow-based deck completion via conditional generation in embedding space.

Instead of pure discrete flow matching (which requires complex categorical
distributions), this uses conditional flow matching in the continuous
embedding space:

1. **Representation**: A deck is represented as the set of card embeddings
   (128D vectors from KeyedVectors). The seed deck provides the condition.

2. **Flow**: Learns a velocity field v(x_t, t | seed) that transports noise
   x_0 ~ N(0, I) to card embeddings x_1 that belong in the completed deck.
   Uses optimal transport conditional flow matching (OT-CFM, Lipman et al. 2023).

3. **Decoding**: Generated embeddings are mapped to discrete cards via
   nearest-neighbor lookup in the vocabulary, with deduplication and
   format constraint enforcement.

Training data: pairs of (seed_deck, full_deck) from the deck corpus.
The model learns to complete partial decks by generating the missing cards.

This is lighter than a full diffusion model -- the flow network is a small
MLP conditioned on the seed deck centroid, and training is fast on CPU.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from .constants import MAGIC_BASIC_LANDS, POKEMON_BASIC_ENERGY
from .deck_completion import _legal_add, _main_partition_name

logger = logging.getLogger("decksage.flow_completion")


@dataclass
class FlowCompletionConfig:
    """Configuration for flow-based deck completion."""

    game: Literal["magic", "yugioh", "pokemon"] = "magic"
    target_main_size: int = 60
    embed_dim: int = 128
    hidden_dim: int = 256
    num_steps: int = 20  # ODE integration steps at inference
    copy_limit: int = 4
    pool_size: int = 200  # candidate pool for nearest-neighbor decoding
    temperature: float = 0.5  # sampling temperature (lower = more deterministic)
    seed_fraction: float = 0.5  # fraction of deck used as seed during training


class FlowNetwork(nn.Module):
    """Velocity field network for conditional flow matching.

    Predicts v(x_t, t | c) where:
    - x_t is the noised embedding at time t
    - t is the flow time in [0, 1]
    - c is the seed deck condition (centroid embedding)

    Architecture: MLP with time embedding and condition concatenation.
    """

    def __init__(self, embed_dim: int = 128, hidden_dim: int = 256):
        super().__init__()
        self.embed_dim = embed_dim

        # Time embedding (sinusoidal)
        self.time_dim = 32

        # Input: x_t (embed_dim) + t_emb (time_dim) + condition (embed_dim)
        input_dim = embed_dim + self.time_dim + embed_dim

        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, embed_dim),
        )

    def time_embedding(self, t: torch.Tensor) -> torch.Tensor:
        """Sinusoidal time embedding."""
        half = self.time_dim // 2
        freqs = torch.exp(
            -math.log(10000) * torch.arange(half, device=t.device, dtype=torch.float32) / half
        )
        args = t.unsqueeze(-1) * freqs.unsqueeze(0)
        return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)

    def forward(self, x_t: torch.Tensor, t: torch.Tensor, condition: torch.Tensor) -> torch.Tensor:
        """Predict velocity field.

        Args:
            x_t: [B, embed_dim] noised embeddings
            t: [B] time values in [0, 1]
            condition: [B, embed_dim] seed deck centroid

        Returns:
            [B, embed_dim] predicted velocity
        """
        t_emb = self.time_embedding(t)
        inp = torch.cat([x_t, t_emb, condition], dim=-1)
        return self.net(inp)


class FlowDeckCompleter:
    """Deck completion via conditional flow matching.

    Training:
        1. Sample full decks from corpus
        2. Split into seed (condition) and target (cards to predict)
        3. For each target card embedding x_1:
           - Sample t ~ U(0, 1), x_0 ~ N(0, I)
           - Compute x_t = (1-t)*x_0 + t*x_1 (OT interpolation)
           - Train velocity network to predict v = x_1 - x_0
        4. Loss = ||v_pred - (x_1 - x_0)||^2

    Inference:
        1. Start with x_0 ~ N(0, I) for each slot to fill
        2. Integrate ODE: dx/dt = v(x_t, t | seed) using Euler steps
        3. At x_1, find nearest card in vocabulary
        4. Enforce format constraints (copy limits, deck size)
    """

    def __init__(
        self,
        embeddings: Any,  # KeyedVectors
        config: FlowCompletionConfig | None = None,
    ):
        if not HAS_TORCH:
            raise ImportError("torch required for flow completion")

        self.embeddings = embeddings
        self.config = config or FlowCompletionConfig()
        self.embed_dim = self.config.embed_dim

        # Build embedding matrix for nearest-neighbor lookup
        keys = list(embeddings.key_to_index.keys())
        self.vocab = keys
        self.embed_matrix = torch.tensor(
            np.array([embeddings[k] for k in keys]), dtype=torch.float32
        )
        # L2-normalize for cosine similarity
        self.embed_matrix_norm = F.normalize(self.embed_matrix, dim=-1)

        self.model = FlowNetwork(self.embed_dim, self.config.hidden_dim)
        self.trained = False

    def _deck_to_embeddings(self, deck_cards: list[str]) -> torch.Tensor | None:
        """Convert deck card names to embedding matrix."""
        vecs = []
        for card in deck_cards:
            if card in self.embeddings:
                vecs.append(self.embeddings[card])
        if not vecs:
            return None
        return torch.tensor(np.array(vecs), dtype=torch.float32)

    def train(
        self,
        decks: list[list[str]],
        epochs: int = 50,
        batch_size: int = 64,
        lr: float = 1e-3,
    ) -> dict[str, list[float]]:
        """Train the flow network on deck data.

        Args:
            decks: List of decks, each a list of card names (with repeats)
            epochs: Training epochs
            batch_size: Batch size (number of card embeddings per batch)
            lr: Learning rate

        Returns:
            Training metrics dict with loss history.
        """
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        # Preprocess decks: split into (seed_centroid, target_embeddings)
        training_pairs = []
        seed_frac = self.config.seed_fraction

        for deck in decks:
            # Filter to cards in vocabulary
            valid_cards = [c for c in deck if c in self.embeddings]
            if len(valid_cards) < 10:
                continue

            n_seed = max(3, int(len(valid_cards) * seed_frac))
            # Random split
            indices = np.random.permutation(len(valid_cards))
            seed_cards = [valid_cards[i] for i in indices[:n_seed]]
            target_cards = [valid_cards[i] for i in indices[n_seed:]]

            if not target_cards:
                continue

            seed_vecs = np.array([self.embeddings[c] for c in seed_cards])
            seed_centroid = seed_vecs.mean(axis=0)

            for card in target_cards:
                training_pairs.append(
                    (
                        seed_centroid,
                        self.embeddings[card],
                    )
                )

        if not training_pairs:
            raise ValueError("No valid training pairs from deck data")

        logger.info(f"Training flow network: {len(training_pairs)} pairs from {len(decks)} decks")

        # Convert to tensors
        conditions = torch.tensor(np.array([p[0] for p in training_pairs]), dtype=torch.float32)
        targets = torch.tensor(np.array([p[1] for p in training_pairs]), dtype=torch.float32)

        loss_history = []
        n = len(training_pairs)

        for epoch in range(epochs):
            perm = torch.randperm(n)
            epoch_loss = 0.0
            n_batches = 0

            for i in range(0, n, batch_size):
                idx = perm[i : i + batch_size]
                cond = conditions[idx]
                x_1 = targets[idx]
                b = cond.shape[0]

                # Sample noise and time
                x_0 = torch.randn_like(x_1)
                t = torch.rand(b)

                # OT interpolation: x_t = (1-t)*x_0 + t*x_1
                t_expand = t.unsqueeze(-1)
                x_t = (1 - t_expand) * x_0 + t_expand * x_1

                # Target velocity: v = x_1 - x_0
                v_target = x_1 - x_0

                # Predict velocity
                v_pred = self.model(x_t, t, cond)

                # MSE loss
                loss = F.mse_loss(v_pred, v_target)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            avg_loss = epoch_loss / max(n_batches, 1)
            loss_history.append(avg_loss)

            if (epoch + 1) % 10 == 0:
                logger.info(f"  Epoch {epoch + 1}/{epochs}: loss={avg_loss:.6f}")

        self.trained = True
        return {"loss": loss_history}

    @torch.no_grad()
    def complete(
        self,
        seed_cards: list[str],
        n_cards: int = 30,
        temperature: float | None = None,
    ) -> list[tuple[str, float]]:
        """Complete a deck by generating card embeddings via flow.

        Args:
            seed_cards: List of card names in the seed deck
            n_cards: Number of cards to generate
            temperature: Sampling temperature (default from config)

        Returns:
            List of (card_name, score) tuples for suggested additions.
        """
        if not self.trained:
            raise RuntimeError("Model not trained. Call train() first.")

        self.model.eval()
        temp = temperature or self.config.temperature

        # Compute seed centroid
        seed_vecs = []
        for c in seed_cards:
            if c in self.embeddings:
                seed_vecs.append(self.embeddings[c])
        if not seed_vecs:
            return []

        centroid = np.mean(seed_vecs, axis=0)
        condition = torch.tensor(centroid, dtype=torch.float32).unsqueeze(0)
        condition = condition.expand(n_cards, -1)

        # Start from noise
        x = torch.randn(n_cards, self.embed_dim) * temp

        # Euler integration of the ODE
        dt = 1.0 / self.config.num_steps
        for step in range(self.config.num_steps):
            t = torch.full((n_cards,), step * dt)
            v = self.model(x, t, condition)
            x = x + v * dt

        # Decode: find nearest cards in vocabulary
        x_norm = F.normalize(x, dim=-1)
        sims = x_norm @ self.embed_matrix_norm.T  # [n_cards, vocab_size]

        # Greedy assignment with deduplication
        seed_set = set(seed_cards)
        results = []
        used_counts: dict[str, int] = {}
        copy_limit = self.config.copy_limit

        for i in range(n_cards):
            scores, indices = sims[i].sort(descending=True)
            for score, idx in zip(scores, indices):
                card = self.vocab[idx.item()]
                if card in seed_set:
                    continue
                count = used_counts.get(card, 0)
                if count >= copy_limit:
                    continue
                used_counts[card] = count + 1
                results.append((card, float(score)))
                break

        return results

    def save(self, path: str) -> None:
        """Save trained model."""
        if not self.trained:
            raise RuntimeError("Model not trained")
        torch.save(
            {
                "model_state": self.model.state_dict(),
                "config": {
                    "embed_dim": self.config.embed_dim,
                    "hidden_dim": self.config.hidden_dim,
                    "num_steps": self.config.num_steps,
                },
            },
            path,
        )

    def load(self, path: str) -> None:
        """Load trained model."""
        checkpoint = torch.load(path, weights_only=True)
        self.model.load_state_dict(checkpoint["model_state"])
        self.trained = True
