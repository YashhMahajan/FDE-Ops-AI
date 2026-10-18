"""Embedders and an in-memory vector index.

``HashingEmbedder`` is a deterministic, dependency-free *lexical* baseline (signed feature hashing
of unigrams and bigrams). It is not semantic; real semantic embedders plug in through the same
``Embedder`` protocol as optional extras.
"""

import hashlib
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol

import numpy as np

from fdeops.retrieval.tokenize import tokenize


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> list[str]:
        toks = tokenize(text)
        return toks + [f"{a}_{b}" for a, b in pairwise(toks)]

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float64)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class VectorIndex:
    def __init__(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        self.ids = list(ids)
        self.vectors = vectors

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        sims = self.vectors @ vector
        order = sorted(range(len(self.ids)), key=lambda i: (-sims[i], self.ids[i]))
        return [(self.ids[i], float(sims[i])) for i in order[:k] if sims[i] > 0]
