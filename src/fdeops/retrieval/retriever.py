"""Retrieval over a versioned knowledge base.

What gets indexed is a deployment decision, and a frequent source of real incidents:
``include_superseded=True`` models the common situation where a policy document is updated but the
old version stays in the index. ``freshness_filter`` is the remediation: drop chunks superseded as
of query time. Every result reports whether it is stale, so stale-knowledge failures can be
attributed precisely.
"""

from datetime import date
from typing import Literal

from fdeops.core.model import FrozenModel
from fdeops.retrieval.bm25 import BM25Index
from fdeops.retrieval.embeddings import Embedder, HashingEmbedder, VectorIndex
from fdeops.retrieval.kb import KnowledgeBase, Section


class RetrievalConfig(FrozenModel):
    mode: Literal["bm25", "dense", "hybrid"] = "hybrid"
    top_k: int = 4
    rrf_k: int = 60
    include_superseded: bool = True
    freshness_filter: bool = False
    index_as_of: date | None = None


class RetrievedChunk(FrozenModel):
    section_key: str
    version: int
    uid: str
    title: str
    text: str
    score: float
    rank: int
    stale: bool


class Retriever:
    def __init__(
        self, kb: KnowledgeBase, config: RetrievalConfig, embedder: Embedder | None = None
    ) -> None:
        self.kb = kb
        self.config = config
        self.embedder = embedder or HashingEmbedder()
        self.sections = self._select_sections()
        self._by_uid = {s.uid: s for s in self.sections}
        texts = [(s.uid, f"{s.title}\n{s.text}") for s in self.sections]
        self._bm25 = BM25Index(texts)
        vectors = self.embedder.embed([t for _, t in texts]) if texts else None
        self._dense = VectorIndex([u for u, _ in texts], vectors) if vectors is not None else None

    def _select_sections(self) -> list[Section]:
        cutoff = self.config.index_as_of
        if self.config.include_superseded:
            return [s for s in self.kb.sections if cutoff is None or s.effective_from <= cutoff]
        if cutoff is None:
            latest = max((s.effective_from for s in self.kb.sections), default=None)
            return self.kb.as_of(latest) if latest else []
        return self.kb.as_of(cutoff)

    def _ranked(self, query: str) -> list[tuple[str, float]]:
        n = len(self.sections)
        if self.config.mode == "bm25":
            return self._bm25.search(query, n)
        dense = self._dense.search(self.embedder.embed([query])[0], n) if self._dense else []
        if self.config.mode == "dense":
            return dense
        fused: dict[str, float] = {}
        for ranking in (self._bm25.search(query, n), dense):
            for rank, (uid, _) in enumerate(ranking, start=1):
                fused[uid] = fused.get(uid, 0.0) + 1.0 / (self.config.rrf_k + rank)
        return sorted(fused.items(), key=lambda x: (-x[1], x[0]))

    def search(self, query: str, now: date) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for uid, score in self._ranked(query):
            s = self._by_uid[uid]
            stale = self.kb.is_stale(s, now)
            if stale and self.config.freshness_filter:
                continue
            out.append(
                RetrievedChunk(
                    section_key=s.key,
                    version=s.version,
                    uid=uid,
                    title=s.title,
                    text=s.text,
                    score=score,
                    rank=len(out) + 1,
                    stale=stale,
                )
            )
            if len(out) == self.config.top_k:
                break
        return out
