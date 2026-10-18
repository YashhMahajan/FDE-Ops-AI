import re
import shutil
from pathlib import Path

from fdeops.agent.config import load_agent_config
from fdeops.eval.report import save_run
from fdeops.eval.runner import run_eval
from fdeops.tenancy.loader import load_tenant
from fdeops.trace.redact import PIIConfig, redact_text, redact_value

ROOT = Path(__file__).parents[2]


def test_redact_text_named_patterns() -> None:
    cfg = PIIConfig(redact=True)
    text = "Mail ana.cruz@acorn-labs.example or call +1 (415) 555-0134. Card 4111 1111 1111 1111."
    out = redact_text(text, cfg)
    assert "ana.cruz" not in out and "555-0134" not in out and "4111" not in out
    assert "[EMAIL]" in out and "[PHONE]" in out and "[CARD]" in out


def test_ids_and_money_are_not_phone_numbers() -> None:
    cfg = PIIConfig(redact=True)
    text = "Invoice inv_x9d09bca2c3 for $1,188.00 paid on 2026-09-15, tracking PP123456789."
    assert redact_text(text, cfg) == text


def test_custom_pattern_and_nested_values() -> None:
    cfg = PIIConfig(redact=True, custom={"ADDRESS": r"\d+ [A-Z][a-z]+ (Street|Road)"})
    value = {"a": ["12 Harbor Street", {"b": "x@y.example"}], "n": 3}
    assert redact_value(value, cfg) == {"a": ["[ADDRESS]", {"b": "[EMAIL]"}], "n": 3}


def test_stored_run_has_no_pii_but_scores_used_raw_text(tmp_path: Path) -> None:
    root = tmp_path / "ledgerloop"
    shutil.copytree(ROOT / "tenants/ledgerloop", root)
    cfg_file = root / "tenant.yaml"
    cfg_file.write_text(cfg_file.read_text() + "pii:\n  redact: true\n")
    tenant = load_tenant(root)
    ds = tenant.build_datasets("support-core")["dev"]
    ds = ds.model_copy(
        update={"cases": tuple(c for c in ds.cases if c.scenario == "unknown_requester")}
    )
    config = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
    run = run_eval(tenant, config, ds, tenant.pack.heuristic_model(0, {}))
    assert all(r.success for r in run.results)  # facts were scored before redaction
    stored = (save_run(run, tmp_path / "runs") / "run.json").read_text()
    emails = {c.ticket.requester_email for c in ds.cases}
    assert not any(e in stored for e in emails)
    assert not re.search(r"[\w.+-]+@[\w-]+\.example", stored)
