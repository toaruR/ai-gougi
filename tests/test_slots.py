import asyncio

import pytest

from ai_gougi.slots import SlotPool


def test_reserve_table():
    got = []
    for running, need in [(0, 3), (1, 3), (2, 1), (3, 1)]:
        p = SlotPool(3)
        p.running = running
        got.append(p.try_reserve(need))
    assert got == [True, False, True, False]


def test_release_no_negative():
    p = SlotPool(3)
    for _ in range(5):
        assert p.try_reserve(2)
        p.release(2)
        assert p.running == 0
    with pytest.raises(RuntimeError):
        with p.reserved(2) as ok:
            assert ok and p.running == 2
            raise RuntimeError("x")
    assert p.running == 0
    p.try_reserve(3)
    with p.reserved(1) as ok:
        assert ok is False
    assert p.running == 3


def test_gather_10_max3():
    p = SlotPool(3)
    seen = []

    async def one():
        ok = p.try_reserve(1)
        seen.append(p.running)
        await asyncio.sleep(0.01)
        if ok:
            p.release(1)
        return ok

    async def main():
        return await asyncio.gather(*[one() for _ in range(10)])

    res = asyncio.run(main())
    assert sum(res) <= 3
    assert max(seen) <= 3


def test_env_override_max1(monkeypatch):
    monkeypatch.setenv("AI_GOUGI_MAX_CONCURRENT_PROCS", "1")
    p = SlotPool()
    p.running = 0
    assert p.try_reserve(2) is False


def test_release_underflow_raises():
    p = SlotPool(3)
    with pytest.raises(ValueError):
        p.release(1)
    assert p.running == 0
