from pathlib import Path

import pytest
from pydantic import ValidationError

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import FdeOpsError
from fdeops.devtools.ste import check_text, load_rules
from fdeops.eval.incidents import load_incident
from fdeops.eval.runner import RunResult, run_eval
from fdeops.eval.stats import newcombe_diff
from fdeops.monitor.config import MonitorConfig, MonitorSpec, load_monitors
from fdeops.monitor.detect import cusum_alarm, detect, detection_quality
from fdeops.monitor.report import monitor_runs, render_monitor
from fdeops.monitor.signals import RATE_SIGNALS, TrialSignals
from fdeops.tenancy.loader import Tenant, load_tenant

ROOT = Path(__file__).parents[2]


def sig(i: int, failed: bool = False, **flags: bool) -> TrialSignals:
    return TrialSignals(
        case_id=f"c{i}",
        trial=0,
        scenario="s",
        flags={k: flags.get(k, False) for k in RATE_SIGNALS},
        values={"latency_ms": 1000.0, "tokens": 100.0, "steps": 3.0},
        failed=failed,
    )


def spec(**kw: object) -> MonitorSpec:
    base: dict[str, object] = {"signal": "policy_flag", "tolerance": 0.02, "why": "test"}
    return MonitorSpec.model_validate(base | kw)


def test_newcombe_interval_contains_difference_and_behaves_at_zero() -> None:
    d, lo, hi = newcombe_diff(10, 100, 0, 100)
    assert d == pytest.approx(0.1) and 0 < lo < d < hi
    d, lo, hi = newcombe_diff(0, 50, 0, 50)
    assert d == 0 and lo < 0 < hi


def test_cusum_alarms_on_a_shift_and_not_on_stable_traffic() -> None:
    stable = [i % 20 == 0 for i in range(200)]  # 5%, the reference rate
    assert cusum_alarm(stable, 0.05, 0.10, "up", 3.0) is None
    shifted = stable[:50] + [i % 3 == 0 for i in range(150)]  # 33% after ticket 50
    hit = cusum_alarm(shifted, 0.05, 0.10, "up", 3.0)
    assert hit is not None and 50 < hit < 80


def test_cusum_down_detects_a_drop() -> None:
    assert cusum_alarm([False] * 100, 0.30, 0.10, "down", 3.0) is not None
    assert cusum_alarm([False] * 100, 0.30, 0.10, "up", 3.0) is None


def test_alert_needs_the_full_interval_outside_tolerance() -> None:
    ref = [sig(i) for i in range(100)]
    one = [sig(i, policy_flag=i == 0) for i in range(100)]  # 1% is noise at n=100
    many = [sig(i, policy_flag=i % 5 == 0) for i in range(100)]
    cfg = MonitorConfig(monitors=(spec(),))
    assert detect(cfg, ref, one)[0][0].status == "ok"
    res = detect(cfg, ref, many)[0][0]
    assert res.status == "alert" and res.lo > 0.02 and res.detected_after is not None


def test_too_few_samples_is_not_an_alert() -> None:
    ref = [sig(i) for i in range(10)]
    cur = [sig(i, policy_flag=True) for i in range(10)]
    assert detect(MonitorConfig(monitors=(spec(),)), ref, cur)[0][0].status == "too few samples"


def test_value_monitor_alerts_on_latency_rise_and_not_measured_at_zero() -> None:
    ref = [sig(i) for i in range(60)]
    slow = [s.model_copy(update={"values": {**s.values, "latency_ms": 3000.0}}) for s in ref]
    cfg = MonitorConfig(monitors=(spec(signal="latency_ms", statistic="p95", tolerance=0.25),))
    assert detect(cfg, ref, slow)[0][0].status == "alert"
    zero = [s.model_copy(update={"values": {**s.values, "latency_ms": 0.0}}) for s in ref]
    assert detect(cfg, zero, slow)[0][0].status == "not measured"


def test_silent_failures_are_counted_with_a_review_sample() -> None:
    cur = [sig(i, failed=i < 4, policy_flag=i < 2) for i in range(100)]
    q = detection_quality(cur, ["policy_flag"])
    assert (q.failures, q.seen, q.silent) == (4, 2, 2)
    assert q.review_sample is not None and q.review_sample > 100
    pf = next(s for s in q.signals if s.signal == "policy_flag")
    assert pf.precision == 1.0 and pf.recall == 0.5


def test_config_rejects_unknown_signal_and_missing_why() -> None:
    with pytest.raises(ValidationError):
        spec(signal="latency_ms")  # a value signal needs a value statistic
    with pytest.raises(ValidationError):
        spec(why=" ")


@pytest.mark.parametrize("tenant_id", ["ledgerloop", "parcelpoint"])
def test_tenant_monitor_files_load(tenant_id: str) -> None:
    assert load_monitors(ROOT / "tenants" / tenant_id / "monitors.yaml").monitors


@pytest.fixture(scope="module")
def runs() -> tuple[Tenant, RunResult, RunResult]:
    t = load_tenant(ROOT / "tenants/ledgerloop")
    c = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
    ds = t.build_datasets("support-core")["test"]
    llm = t.pack.heuristic_model(0, {})
    inc = load_incident(ROOT / "incidents/ledgerloop/refund-window-drift.yaml")
    return t, run_eval(t, c, ds, llm), run_eval(t, c, ds, llm, incident=inc)


def test_drift_incident_raises_alerts_and_clean_traffic_does_not(
    runs: tuple[Tenant, RunResult, RunResult],
) -> None:
    t, ref, cur = runs
    rep = monitor_runs(t, ref, cur)
    alerted = {r.signal for r in rep.alerts}
    assert {"stale_context", "critical_flag"} <= alerted
    stale = next(r for r in rep.alerts if r.signal == "stale_context")
    critical = next(r for r in rep.alerts if r.signal == "critical_flag")
    # Superseded context is visible before the wrong refunds.
    assert stale.detected_after is not None and critical.detected_after is not None
    assert stale.detected_after < critical.detected_after
    assert monitor_runs(t, ref, ref).alerts == []
    findings = check_text(render_monitor(rep), load_rules(), "<monitor>")
    assert findings == [], "\n".join(str(f) for f in findings[:10])


def test_monitor_rejects_runs_of_another_tenant(
    runs: tuple[Tenant, RunResult, RunResult],
) -> None:
    _, ref, cur = runs
    other = load_tenant(ROOT / "tenants/parcelpoint")
    with pytest.raises(FdeOpsError):
        monitor_runs(other, ref, cur)


def test_monitor_cli_exits_2_on_page_alert(
    runs: tuple[Tenant, RunResult, RunResult], tmp_path: Path
) -> None:
    from typer.testing import CliRunner

    from fdeops.cli.main import app
    from fdeops.eval.report import save_run

    _, ref, cur = runs
    a, b = save_run(ref, tmp_path), save_run(cur, tmp_path)
    tenant = str(ROOT / "tenants/ledgerloop")
    res = CliRunner().invoke(app, ["monitor", str(a), str(b), "--tenant", tenant])
    assert res.exit_code == 2, res.output
    assert (b / "monitor.md").exists() and "critical_flag" in res.output
    calm = CliRunner().invoke(app, ["monitor", str(a), str(a), "--tenant", tenant])
    assert calm.exit_code == 0, calm.output
