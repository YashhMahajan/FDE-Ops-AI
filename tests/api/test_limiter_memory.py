from fdeops.api.security import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_idle_buckets_are_dropped_so_memory_stays_bounded() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=5, clock=clock, max_buckets=1_000)
    for i in range(10_000):
        clock.now += 0.001
        limiter.allow(f"ip:10.0.{i // 256}.{i % 256}")
    assert len(limiter._buckets) <= 1_000


def test_a_client_that_used_its_tokens_is_not_forgotten() -> None:
    """Dropping a bucket must not give a client a free refill: only full buckets are dropped."""
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=3, clock=clock, max_buckets=50)
    for _ in range(3):
        assert limiter.allow("key:abuser")[0]
    assert not limiter.allow("key:abuser")[0]
    for i in range(500):  # many other clients push the table over its size
        clock.now += 0.0001
        limiter.allow(f"ip:{i}")
    assert not limiter.allow("key:abuser")[0]


def test_a_full_bucket_that_was_dropped_behaves_like_a_new_one() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=3, clock=clock, max_buckets=10)
    assert limiter.allow("key:a")[0]
    clock.now += 120  # long enough to refill
    for i in range(50):
        limiter.allow(f"ip:{i}")
    assert [limiter.allow("key:a")[0] for _ in range(3)] == [True, True, True]
