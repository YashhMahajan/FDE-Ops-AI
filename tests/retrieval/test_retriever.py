from datetime import date
from pathlib import Path

import numpy as np

from fdeops.retrieval.bm25 import BM25Index
from fdeops.retrieval.embeddings import HashingEmbedder
from fdeops.retrieval.kb import load_kb
from fdeops.retrieval.retriever import RetrievalConfig, Retriever
from fdeops.retrieval.tokenize import tokenize

KB = Path(__file__).parents[2] / "tenants" / "ledgerloop" / "kb"
TODAY = date(2026, 9, 15)


def test_tokenize_keeps_digits_drops_stopwords() -> None:
    assert tokenize("The refund is within 14 days!") == ["refund", "within", "14", "days"]


def test_bm25_ranks_exact_term_first() -> None:
    idx = BM25Index([("a", "cats and dogs"), ("b", "refund window policy"), ("c", "dogs only")])
    hits = idx.search("refund policy", k=3)
    assert hits[0][0] == "b"
    assert all(score > 0 for _, score in hits)
    assert idx.search("zebra", k=3) == []


def test_hashing_embedder_deterministic_normalized() -> None:
    e = HashingEmbedder(dim=256)
    a = e.embed(["refund my invoice"])
    b = e.embed(["refund my invoice"])
    assert np.allclose(a, b)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)
    assert e.embed([""]).shape == (1, 256)


def test_hybrid_rrf_merges() -> None:
    r = Retriever(load_kb(KB), RetrievalConfig(mode="hybrid", top_k=3))
    hits = r.search("how do I update my card after a failed payment", TODAY)
    assert hits[0].section_key.startswith("payment-failures#")
    assert [h.rank for h in hits] == [1, 2, 3]
    assert len({h.uid for h in hits}) == len(hits)


def test_superseded_version_marked_stale() -> None:
    r = Retriever(load_kb(KB), RetrievalConfig(mode="bm25", top_k=6, include_superseded=True))
    hits = [
        h
        for h in r.search("refund window days payment", TODAY)
        if h.section_key == "refund-policy#refund-window"
    ]
    assert {h.version for h in hits} == {1, 2}
    assert {h.version: h.stale for h in hits} == {1: True, 2: False}


def test_freshness_filter_removes_stale() -> None:
    r = Retriever(
        load_kb(KB),
        RetrievalConfig(mode="bm25", top_k=6, include_superseded=True, freshness_filter=True),
    )
    assert all(not h.stale for h in r.search("refund window days payment", TODAY))


def test_current_only_index() -> None:
    r = Retriever(
        load_kb(KB),
        RetrievalConfig(mode="bm25", top_k=6, include_superseded=False, index_as_of=TODAY),
    )
    versions = {
        h.version
        for h in r.search("refund window", TODAY)
        if h.section_key == "refund-policy#refund-window"
    }
    assert versions == {2}


def test_index_as_of_before_drift_has_only_old_policy() -> None:
    r = Retriever(
        load_kb(KB),
        RetrievalConfig(
            mode="bm25", top_k=6, include_superseded=False, index_as_of=date(2026, 8, 1)
        ),
    )
    hits = [
        h
        for h in r.search("refund window", TODAY)
        if h.section_key == "refund-policy#refund-window"
    ]
    assert [h.version for h in hits] == [1]
    assert hits[0].stale  # stale relative to query time
