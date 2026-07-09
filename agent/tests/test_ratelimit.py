"""Rate limiter: per-IP hourly cap and a global daily backstop."""
from __future__ import annotations

from app.ratelimit import RateLimiter


def test_per_ip_hourly_cap():
    rl = RateLimiter(per_ip_hour=2, global_day=100)
    assert rl.allow("1.2.3.4")[0]
    assert rl.allow("1.2.3.4")[0]
    ok, reason = rl.allow("1.2.3.4")
    assert not ok and "hourly" in reason.lower()
    # A different IP is unaffected.
    assert rl.allow("5.6.7.8")[0]


def test_global_daily_backstop():
    rl = RateLimiter(per_ip_hour=100, global_day=2)
    assert rl.allow("a")[0]
    assert rl.allow("b")[0]
    ok, reason = rl.allow("c")  # under the per-IP cap, but the global cap is hit
    assert not ok and "daily" in reason.lower()
