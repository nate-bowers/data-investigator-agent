"""A tiny in-memory rate limiter for the public /investigate endpoint.

That endpoint calls a paid API, so an unthrottled public URL is a real cost risk
(CORS only stops *browsers* from other origins; anyone can curl the backend). This
caps runs per IP per hour AND total runs per day (a global backstop), so neither a
single visitor nor the whole internet can run up the bill.

In-memory is fine here: the free backend is a single instance. The Anthropic Console
spend cap is the hard dollar-backstop underneath this.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from . import config


class RateLimiter:
    def __init__(self, per_ip_hour: int, global_day: int) -> None:
        self.per_ip_hour = per_ip_hour
        self.global_day = global_day
        self._ip: dict[str, deque[float]] = defaultdict(deque)
        self._global: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, ip: str) -> tuple[bool, str]:
        """Return (allowed, reason). Records the hit when allowed."""
        now = time.time()
        with self._lock:
            # Global daily backstop.
            g = self._global
            day_ago = now - 86400
            while g and g[0] < day_ago:
                g.popleft()
            if len(g) >= self.global_day:
                return False, "The demo has hit its daily limit. Try the recorded run."

            # Per-IP hourly limit.
            hour_ago = now - 3600
            dq = self._ip[ip]
            while dq and dq[0] < hour_ago:
                dq.popleft()
            if len(dq) >= self.per_ip_hour:
                return False, "You've hit the hourly limit. Try the recorded run."

            dq.append(now)
            g.append(now)
            # Light cleanup so idle IPs don't accumulate forever.
            if len(self._ip) > 5000:
                for k in [k for k, v in self._ip.items() if not v]:
                    del self._ip[k]
            return True, ""


limiter = RateLimiter(config.RATE_LIMIT_PER_IP_HOUR, config.RATE_LIMIT_GLOBAL_DAY)

# Separate, generous bucket for cheap read/parse endpoints (/context, /upload) so
# normal page loads never spend the paid /investigate budget.
cheap_limiter = RateLimiter(config.RATE_LIMIT_CHEAP_PER_IP_HOUR, config.RATE_LIMIT_CHEAP_GLOBAL_DAY)
