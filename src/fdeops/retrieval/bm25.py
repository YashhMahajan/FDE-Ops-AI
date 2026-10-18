"""Okapi BM25, implemented directly: about forty lines, and every scoring decision is visible."""

import math
from collections import Counter
from collections.abc import Sequence

from fdeops.retrieval.tokenize import tokenize


class BM25Index:
    def __init__(self, items: Sequence[tuple[str, str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.ids = [i for i, _ in items]
        self.docs = [Counter(tokenize(text)) for _, text in items]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        # BM25+ style floor keeps idf positive for terms present in most documents.
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            s = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                    s += self.idf[t] * tf * (self.k1 + 1) / norm
            out.append(s)
        return out

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        ranked = sorted(zip(self.ids, self.scores(query), strict=True), key=lambda x: (-x[1], x[0]))
        return [(i, s) for i, s in ranked if s > 0][:k]
