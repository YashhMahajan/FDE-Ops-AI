from fdeops.devtools.ste import check_text, load_rules
from fdeops.diagnose.interventions import diagnose_run
from fdeops.diagnose.report import render_diagnosis
from fdeops.eval.compare import compare_runs, render_comparison
from fdeops.eval.report import render_markdown, summarize
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import CLEAN, STALE, run, subset

RULES = load_rules()


def assert_ste(text: str) -> None:
    findings = check_text(text, RULES, "<generated>")
    assert findings == [], "\n".join(str(f) for f in findings[:15])


def test_generated_reports_obey_ste(tenant: Tenant, dev: Dataset) -> None:
    ds = subset(dev, "refund_outside_window", "refund_eligible", "invoice_explain")
    a = run(tenant, ds, config=STALE, trials=2)
    b = run(tenant, ds, config=CLEAN, trials=2)
    assert_ste(render_markdown(summarize(a)))
    assert_ste(render_comparison(compare_runs(a, b)))
    assert_ste(render_diagnosis(diagnose_run(tenant, a, ds, tenant.pack.heuristic_model(0, {}))))
