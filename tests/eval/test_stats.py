import pytest

from fdeops.eval.stats import (
    cohens_kappa,
    holm,
    mcnemar_exact,
    mde_two_proportions,
    n_for_ci_half_width,
    paired_bootstrap_diff,
    pass_hat_k,
    rule_of_three_upper,
    wilson_interval,
)


def test_wilson_known_value() -> None:
    lo, hi = wilson_interval(8, 10)
    assert lo == pytest.approx(0.490, abs=1e-3)
    assert hi == pytest.approx(0.943, abs=1e-3)


def test_wilson_edges() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(0, 20)
    assert lo == 0.0 and 0 < hi < 0.2
    lo, hi = wilson_interval(20, 20)
    assert hi == pytest.approx(1.0) and lo > 0.8


def test_mcnemar_known_value() -> None:
    assert mcnemar_exact(1, 9) == pytest.approx(22 / 1024)
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)


def test_cohens_kappa_textbook() -> None:
    a = [True] * 20 + [True] * 5 + [False] * 10 + [False] * 15
    b = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohens_kappa(a, b) == pytest.approx(0.4)
    assert cohens_kappa([True, False], [True, False]) == pytest.approx(1.0)
    assert cohens_kappa([True, True], [True, True]) == 1.0  # degenerate: perfect agreement


def test_pass_hat_k() -> None:
    assert pass_hat_k([3, 3], n_trials=3, k=3) == 1.0
    assert pass_hat_k([1, 2], n_trials=3, k=3) == 0.0
    assert pass_hat_k([2], n_trials=3, k=1) == pytest.approx(2 / 3)
    assert pass_hat_k([2], n_trials=3, k=2) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        pass_hat_k([1], n_trials=2, k=3)


def test_holm_adjusts_and_is_monotone() -> None:
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    assert holm([]) == []


def test_rule_of_three() -> None:
    assert rule_of_three_upper(100) == pytest.approx(0.03)
    assert rule_of_three_upper(0) == 1.0
    assert rule_of_three_upper(2) == 1.0


def test_paired_bootstrap_contains_true_shift() -> None:
    a = [0.0] * 200
    b = [1.0 if i % 10 < 3 else 0.0 for i in range(200)]
    d = paired_bootstrap_diff(a, b, n_resamples=4000, seed=1)
    assert d.mean == pytest.approx(0.3)
    assert d.lo < 0.3 < d.hi and d.lo > 0.2
    assert d.n == 200
    with pytest.raises(ValueError):
        paired_bootstrap_diff([1.0], [1.0, 2.0])


def test_bootstrap_deterministic() -> None:
    a = [((i * 37) % 11) / 10 for i in range(40)]
    b = [((i * 53) % 13) / 12 for i in range(40)]
    assert paired_bootstrap_diff(a, b, seed=3) == paired_bootstrap_diff(a, b, seed=3)
    # The seed is used: a different seed gives a different interval.
    assert paired_bootstrap_diff(a, b, seed=3) != paired_bootstrap_diff(a, b, seed=4)


def test_sample_size_and_mde() -> None:
    assert n_for_ci_half_width(0.05) == 385
    m100 = mde_two_proportions(100, 0.8)
    m400 = mde_two_proportions(400, 0.8)
    assert 0.12 < m100 < 0.2
    assert m400 < m100
