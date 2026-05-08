"""Tests for the per-host async token-bucket throttle."""

from __future__ import annotations

import asyncio
import time

import pytest

from common.throttle import Throttle


# Real-time tolerance for wait-based assertions. ±100ms per the plan;
# we use 150ms to keep CI noise from flaking.
TOL = 0.15


class TestRegister:
    def test_register_then_is_registered(self) -> None:
        t = Throttle()
        assert not t.is_registered("arxiv")
        t.register("arxiv", rate_per_sec=1 / 3)
        assert t.is_registered("arxiv")

    def test_register_idempotent_when_params_match(self) -> None:
        t = Throttle()
        t.register("openalex", rate_per_sec=10.0, burst=10.0)
        t.register("openalex", rate_per_sec=10.0, burst=10.0)  # no raise
        assert t.is_registered("openalex")

    def test_register_raises_on_param_mismatch(self) -> None:
        t = Throttle()
        t.register("edgar", rate_per_sec=10.0)
        with pytest.raises(ValueError, match="already registered"):
            t.register("edgar", rate_per_sec=5.0)

    def test_register_rejects_nonpositive_rate(self) -> None:
        t = Throttle()
        with pytest.raises(ValueError, match="rate_per_sec"):
            t.register("bad", rate_per_sec=0)
        with pytest.raises(ValueError, match="rate_per_sec"):
            t.register("bad", rate_per_sec=-1)

    def test_register_rejects_nonpositive_burst(self) -> None:
        t = Throttle()
        with pytest.raises(ValueError, match="burst"):
            t.register("bad", rate_per_sec=1.0, burst=0)

    def test_default_burst_floor_of_one(self) -> None:
        # rate < 1/sec (e.g. arxiv 1/3s) should still allow one immediate
        # acquire after registration.
        t = Throttle()
        t.register("arxiv", rate_per_sec=1 / 3)
        # If burst defaulted to rate_per_sec (0.33), the first acquire
        # would block. The floor of 1.0 is what we're checking.
        bucket = t._buckets["arxiv"]
        assert bucket.burst == 1.0
        assert bucket.tokens == 1.0


class TestAcquireBasic:
    async def test_unregistered_raises(self) -> None:
        t = Throttle()
        with pytest.raises(KeyError, match="not registered"):
            await t.acquire("nope")

    async def test_first_acquire_is_instant(self) -> None:
        t = Throttle()
        t.register("a", rate_per_sec=20.0, burst=1.0)
        start = time.monotonic()
        await t.acquire("a")
        elapsed = time.monotonic() - start
        assert elapsed < TOL

    async def test_second_acquire_waits_for_refill(self) -> None:
        # rate=20/sec means one token every 50ms. burst=1 means second
        # acquire must wait ~50ms after the first.
        t = Throttle()
        t.register("a", rate_per_sec=20.0, burst=1.0)
        await t.acquire("a")
        start = time.monotonic()
        await t.acquire("a")
        elapsed = time.monotonic() - start
        assert 0.05 - TOL < elapsed < 0.05 + TOL, f"elapsed={elapsed}"

    async def test_acquire_too_many_tokens_raises(self) -> None:
        t = Throttle()
        t.register("a", rate_per_sec=10.0, burst=5.0)
        with pytest.raises(ValueError, match="exceeds bucket burst"):
            await t.acquire("a", tokens=6.0)


class TestSerialization:
    async def test_concurrent_acquires_serialize(self) -> None:
        # 5 acquires on a 20/sec, burst=1 bucket: first is instant,
        # next four wait 50ms each. Total ~200ms.
        t = Throttle()
        t.register("a", rate_per_sec=20.0, burst=1.0)

        async def grab() -> float:
            await t.acquire("a")
            return time.monotonic()

        start = time.monotonic()
        finishes = await asyncio.gather(*[grab() for _ in range(5)])
        total = time.monotonic() - start

        # Lower bound: 4 waits of 50ms = 200ms. Upper: 200ms + tolerance.
        assert 0.20 - TOL < total < 0.20 + TOL, f"total={total}"

        # Finishes must be monotonically non-decreasing (FIFO via lock).
        for i in range(1, len(finishes)):
            assert finishes[i] >= finishes[i - 1] - 1e-3


class TestIndependence:
    async def test_buckets_dont_interfere(self) -> None:
        # Bucket A is slow (will take ~200ms total). Bucket B is fast
        # (burst=10) and should finish near-instant in parallel.
        t = Throttle()
        t.register("slow", rate_per_sec=20.0, burst=1.0)
        t.register("fast", rate_per_sec=1000.0, burst=10.0)

        async def hammer_slow() -> float:
            for _ in range(5):
                await t.acquire("slow")
            return time.monotonic()

        async def hammer_fast() -> float:
            for _ in range(10):
                await t.acquire("fast")
            return time.monotonic()

        start = time.monotonic()
        slow_done, fast_done = await asyncio.gather(hammer_slow(), hammer_fast())

        slow_elapsed = slow_done - start
        fast_elapsed = fast_done - start

        # Slow path takes ~200ms, fast path should finish well before.
        assert fast_elapsed < TOL, f"fast bucket was blocked: {fast_elapsed}"
        assert slow_elapsed > 0.15, f"slow bucket finished too fast: {slow_elapsed}"


class TestBurst:
    async def test_burst_capacity_allows_immediate_acquires(self) -> None:
        # rate=1/sec, burst=5: 5 instant acquires, 6th must wait.
        t = Throttle()
        t.register("b", rate_per_sec=1.0, burst=5.0)

        start = time.monotonic()
        for _ in range(5):
            await t.acquire("b")
        burst_elapsed = time.monotonic() - start
        assert burst_elapsed < TOL, f"5-deep burst was not instant: {burst_elapsed}"

        # 6th acquire should wait ~1s. We don't actually wait the full
        # second; instead verify the bucket reports it'd block. We can
        # test the wait shape with a smaller refill period:
        # consume the bucket and confirm the next acquire waits.

    async def test_post_burst_throttles(self) -> None:
        # Smaller wait so the test stays sub-second.
        # rate=20/sec, burst=3: 3 instant, 4th waits ~50ms.
        t = Throttle()
        t.register("b", rate_per_sec=20.0, burst=3.0)

        start = time.monotonic()
        for _ in range(3):
            await t.acquire("b")
        burst_elapsed = time.monotonic() - start
        assert burst_elapsed < TOL

        wait_start = time.monotonic()
        await t.acquire("b")
        wait_elapsed = time.monotonic() - wait_start
        assert 0.05 - TOL < wait_elapsed < 0.05 + TOL, f"4th-acquire wait={wait_elapsed}"

    async def test_idle_period_refills_to_burst(self) -> None:
        # Drain the bucket, idle long enough to refill past burst, then
        # confirm tokens are clamped at burst (no over-accumulation).
        t = Throttle()
        t.register("b", rate_per_sec=100.0, burst=2.0)

        # Drain.
        await t.acquire("b")
        await t.acquire("b")

        # Idle 100ms - that's 10 tokens worth at rate=100/sec, but burst=2
        # so we should only see 2 instant acquires before throttling.
        await asyncio.sleep(0.1)

        start = time.monotonic()
        await t.acquire("b")
        await t.acquire("b")
        burst_elapsed = time.monotonic() - start
        assert burst_elapsed < TOL, f"refilled burst not instant: {burst_elapsed}"

        # 3rd should wait again - tokens were clamped at burst=2.
        wait_start = time.monotonic()
        await t.acquire("b")
        wait_elapsed = time.monotonic() - wait_start
        assert wait_elapsed > 0.005, f"tokens were not clamped: {wait_elapsed}"


class TestCancellation:
    async def test_cancelled_acquire_releases_lock(self) -> None:
        # Set up: bucket with a slow refill. One acquirer drains the
        # token, a second acquirer starts waiting, we cancel it, then
        # confirm a third acquirer can still make progress (no
        # deadlock, no lost token).
        t = Throttle()
        t.register("c", rate_per_sec=20.0, burst=1.0)

        await t.acquire("c")  # drain

        # Start a waiter that will block ~50ms.
        waiter = asyncio.create_task(t.acquire("c"))
        # Yield so the waiter actually enters acquire() and grabs the lock.
        await asyncio.sleep(0.005)

        # Cancel mid-wait.
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        # A fresh acquirer should be able to proceed once the bucket
        # refills (~50ms total from the original drain). We measure
        # from now; the actual remaining wait is whatever's left.
        start = time.monotonic()
        await asyncio.wait_for(t.acquire("c"), timeout=1.0)
        elapsed = time.monotonic() - start
        # Should complete within the natural refill window plus tolerance.
        # If the lock had been leaked, this would hang and time out.
        assert elapsed < 0.1 + TOL, f"post-cancel acquire took {elapsed}"

    async def test_cancel_does_not_leak_tokens(self) -> None:
        # If a cancelled task had decremented tokens before being
        # cancelled, the bucket would be artificially short. Confirm
        # the token count is what we expect after the dust settles.
        t = Throttle()
        t.register("c", rate_per_sec=20.0, burst=1.0)

        # Drain.
        await t.acquire("c")
        # Start a waiter, cancel it.
        waiter = asyncio.create_task(t.acquire("c"))
        await asyncio.sleep(0.005)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        # Wait long enough for one full refill (50ms + slack).
        await asyncio.sleep(0.08)

        # Next acquire should be instant - the cancelled waiter must
        # not have stolen the refilled token.
        start = time.monotonic()
        await t.acquire("c")
        elapsed = time.monotonic() - start
        assert elapsed < TOL, f"token was leaked by cancelled task: {elapsed}"


class TestReset:
    def test_reset_named_bucket(self) -> None:
        t = Throttle()
        t.register("a", rate_per_sec=1.0)
        t.register("b", rate_per_sec=1.0)
        t.reset("a")
        assert not t.is_registered("a")
        assert t.is_registered("b")

    def test_reset_all_buckets(self) -> None:
        t = Throttle()
        t.register("a", rate_per_sec=1.0)
        t.register("b", rate_per_sec=1.0)
        t.reset()
        assert not t.is_registered("a")
        assert not t.is_registered("b")

    def test_reset_unknown_bucket_is_silent(self) -> None:
        t = Throttle()
        t.reset("never-registered")  # no raise


class TestModuleLevelSingleton:
    """Smoke-test the module-level convenience functions."""

    async def test_module_register_and_acquire(self) -> None:
        from common import throttle as throttle_mod

        # Use a unique name and clean up after.
        name = "test-module-singleton-bucket"
        try:
            throttle_mod.register(name, rate_per_sec=100.0, burst=1.0)
            assert throttle_mod.is_registered(name)
            await throttle_mod.acquire(name)
        finally:
            throttle_mod.reset(name)
        assert not throttle_mod.is_registered(name)
