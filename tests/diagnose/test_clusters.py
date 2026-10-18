from fdeops.diagnose.classify import classify_run
from fdeops.diagnose.clusters import cluster_failures
from fdeops.diagnose.taxonomy import FailureClass
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import STALE, run, subset


def test_clusters_group_by_class_and_scenario(tenant: Tenant, dev: Dataset) -> None:
    ds = subset(dev, "refund_eligible", "refund_outside_window")
    r = run(tenant, ds, config=STALE, trials=2, wrong_amount=1.0)
    labels = classify_run(r, tenant.pack.knowledge_rules)
    clusters = cluster_failures(labels, r)
    ids = [c.id for c in clusters]
    assert "bad_arguments:refund_eligible" in ids
    assert "stale_knowledge:refund_outside_window" in ids
    assert sum(c.n_trials for c in clusters) == len(labels)
    assert [c.n_trials for c in clusters] == sorted((c.n_trials for c in clusters), reverse=True)
    stale = next(c for c in clusters if c.failure_class == FailureClass.STALE_KNOWLEDGE)
    assert stale.n_cases == len(stale.case_ids) and stale.tags["drift_sensitive"] == stale.n_trials
    assert 0 < stale.share_of_failures <= 1
    assert stale.examples
