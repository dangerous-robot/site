"""Per-host async token-bucket throttle.

Shared infrastructure for source-pool-expansion-tier1: a small registry of
named token-bucket throttles so each upstream API (arXiv, S2, OpenAlex,
EDGAR, Tavily, Brave, ...) can declare its rate limit once and have every
call site cooperate.

Design notes
------------
- Process-local only. Single pipeline run is the unit. No Redis, no
  cross-process coordination.
- One bucket per logical host/API, identified by a string name. Buckets
  are independent: an `acquire` on bucket A never blocks bucket B.
- Each bucket carries its own `asyncio.Lock`. The bucket math (token
  refill, decrement) and the wait `asyncio.sleep` both run inside the
  lock, so concurrent acquirers serialize fairly (FIFO via the lock's
  waiter queue) and a cancelled acquirer releases the lock without
  having mutated `tokens`.
- `time.monotonic()` is used for clock math (no wall-clock drift, no
  negative deltas across NTP adjustments).
- `register()` is idempotent for matching params and raises on mismatch
  so two import-time registrations of the same bucket don't silently
  diverge. `acquire()` on an unknown name raises `KeyError` rather than
  auto-creating a default bucket - silent defaults would hide config bugs.

Generalises the inline 429 retry loops at
`pipeline/researcher/agent.py:50-55` and
`pipeline/orchestrator/pipeline.py:701-703`. Path-specific wiring lands
with each path commit.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Final


__all__ = [
    "Throttle",
    "default_throttle",
    "register",
    "acquire",
    "reset",
    "is_registered",
]


@dataclass
class _Bucket:
    """A single token-bucket. Internal; do not construct directly."""

    rate_per_sec: float
    burst: float
    tokens: float
    last_refill: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _refill(self, now: float) -> None:
        """Add tokens earned since the last refill, clamped at burst."""
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate_per_sec)
        self.last_refill = now


class Throttle:
    """A registry of named token-bucket throttles.

    Most callers will use the module-level `default_throttle` singleton
    via the `register()` / `acquire()` module functions. Construct a
    fresh `Throttle` instance only when you need an isolated registry
    (e.g., in tests).
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        # Guards bucket creation/removal in the registry. Not held during
        # `acquire()`; that path uses each bucket's own lock so different
        # buckets stay independent.
        self._registry_lock: asyncio.Lock | None = None

    def _ensure_registry_lock(self) -> asyncio.Lock:
        # Lazy: an `asyncio.Lock` created at import time would bind to
        # whatever loop happened to be current then (often none), which
        # breaks under pytest-asyncio's per-test loop. Bind on first use.
        if self._registry_lock is None:
            self._registry_lock = asyncio.Lock()
        return self._registry_lock

    def register(
        self,
        name: str,
        *,
        rate_per_sec: float,
        burst: float | None = None,
    ) -> None:
        """Register a bucket.

        Args:
            name: Identifier used by `acquire()`. Convention: lowercase
                host or API name (e.g., `'arxiv'`, `'openalex'`).
            rate_per_sec: Steady-state token refill rate, in tokens per
                second. For "1 request every 3 seconds", pass `1/3`.
            burst: Maximum tokens the bucket can hold. Defaults to
                `max(1.0, rate_per_sec)` so a 10/s bucket can absorb a
                short burst of 10 immediate acquires after an idle
                period, while a 1/3-per-sec bucket still allows a single
                immediate acquire.

        Idempotent for matching params; raises `ValueError` on mismatch
        so two import-time registrations can't silently diverge.
        """
        if rate_per_sec <= 0:
            raise ValueError(f"rate_per_sec must be > 0, got {rate_per_sec}")
        if burst is None:
            burst = max(1.0, rate_per_sec)
        if burst <= 0:
            raise ValueError(f"burst must be > 0, got {burst}")

        existing = self._buckets.get(name)
        if existing is not None:
            if (
                existing.rate_per_sec == rate_per_sec
                and existing.burst == burst
            ):
                return  # idempotent re-registration
            raise ValueError(
                f"throttle bucket {name!r} already registered with "
                f"rate_per_sec={existing.rate_per_sec}, burst={existing.burst}; "
                f"refusing to overwrite with rate_per_sec={rate_per_sec}, burst={burst}"
            )

        now = time.monotonic()
        self._buckets[name] = _Bucket(
            rate_per_sec=rate_per_sec,
            burst=burst,
            tokens=burst,  # start full so first burst-worth of acquires is instant
            last_refill=now,
        )

    def is_registered(self, name: str) -> bool:
        return name in self._buckets

    async def acquire(self, name: str, tokens: float = 1.0) -> None:
        """Block until `tokens` are available on bucket `name`.

        Holds the bucket's lock across the wait so concurrent acquirers
        serialize FIFO. Honors `asyncio.CancelledError`: if cancelled
        during the sleep, the lock is released (via `async with`) and
        no token is deducted.

        Raises:
            KeyError: if `name` was never registered. Auto-creating a
                default bucket would hide misconfiguration.
            ValueError: if `tokens` exceeds the bucket's burst capacity
                (the request could never be satisfied).
        """
        bucket = self._buckets.get(name)
        if bucket is None:
            raise KeyError(
                f"throttle bucket {name!r} not registered; "
                f"call register({name!r}, rate_per_sec=...) first"
            )
        if tokens <= 0:
            raise ValueError(f"tokens must be > 0, got {tokens}")
        if tokens > bucket.burst:
            raise ValueError(
                f"acquire({name!r}, tokens={tokens}) exceeds bucket burst "
                f"{bucket.burst}; request can never be satisfied"
            )

        async with bucket.lock:
            # Inside the lock: refill, then either deduct immediately or
            # sleep until enough tokens have accumulated. Doing both
            # under the lock means cancellation during sleep leaves
            # `tokens` untouched and lets the next waiter make progress.
            while True:
                now = time.monotonic()
                bucket._refill(now)
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return
                deficit = tokens - bucket.tokens
                wait = deficit / bucket.rate_per_sec
                # `asyncio.sleep` raises CancelledError on cancellation;
                # that propagates out of the `async with` cleanly.
                await asyncio.sleep(wait)
                # Loop and recheck under the lock - clock could have
                # been mocked or sleep could return early on some
                # platforms. The lock guarantees no other waiter
                # consumed tokens in the meantime.

    def reset(self, name: str | None = None) -> None:
        """Drop registered buckets. Tests use this for isolation.

        With `name=None`, clears every bucket. Otherwise drops just the
        named one (silent if absent).
        """
        if name is None:
            self._buckets.clear()
            return
        self._buckets.pop(name, None)


# Module-level singleton. Path code does
#     from common.throttle import register, acquire
#     register('arxiv', rate_per_sec=1/3)
#     ...
#     await acquire('arxiv')
default_throttle: Final[Throttle] = Throttle()


def register(
    name: str,
    *,
    rate_per_sec: float,
    burst: float | None = None,
) -> None:
    """Register a bucket on the module-level singleton."""
    default_throttle.register(name, rate_per_sec=rate_per_sec, burst=burst)


async def acquire(name: str, tokens: float = 1.0) -> None:
    """Acquire `tokens` from bucket `name` on the module-level singleton."""
    await default_throttle.acquire(name, tokens=tokens)


def is_registered(name: str) -> bool:
    """Whether `name` is registered on the module-level singleton."""
    return default_throttle.is_registered(name)


def reset(name: str | None = None) -> None:
    """Drop buckets on the module-level singleton (for tests)."""
    default_throttle.reset(name)
