"""deliberate 前半を fake run_cli で試験する(実 CLI は呼ばない)。"""
import asyncio

import pytest

from ai_gougi.deliberate import run_deliberate
from ai_gougi.schema import make_ask_result, validate_deliberate_output
from ai_gougi.slots import SlotPool

ORDER = ["claude", "codex", "agy"]


def _res(p, ok):
    if ok:
        return make_ask_result(p, ok=True, exit_code=0, stdout=f"op-{p}")
    return make_ask_result(p, ok=False, exit_code=1, error_code="NONZERO_EXIT", error_message="x")


class Fake:
    def __init__(self, ok_set=("claude", "codex", "agy"), delay=0.0, pool=None, boom=None):
        self.ok_set = set(ok_set)
        self.calls = []
        self.delay = delay
        self.pool = pool
        self.cur = 0
        self.peak = 0
        self.boom = boom
        self.reserved_flags = []

    async def __call__(self, participant, prompt, *, pool=None, reserved=False):
        self.calls.append((participant, prompt))
        self.reserved_flags.append(reserved)
        self.cur += 1
        self.peak = max(self.peak, self.cur)
        try:
            await asyncio.sleep(self.delay)
            if self.boom == participant:
                raise RuntimeError("boom")
            return _res(participant, participant in self.ok_set)
        finally:
            self.cur -= 1


def run(theme, rounds, fake, pool=None):
    pool = pool or SlotPool(3)
    return asyncio.run(run_deliberate(theme, rounds, fake, pool=pool)), pool


def test_s1_below_min_stops():
    fake = Fake(ok_set=[])
    out, pool = run("t", 2, fake)
    assert (out["status"], out["error_code"]) == ("failed", "ALL_FAILED")
    assert len(out["rounds"]) == 1 and len(out["rounds"][0]["results"]) == 3
    assert len(fake.calls) == 3 and pool.running == 0
    fake = Fake(ok_set=["codex"])
    out, pool = run("t", 2, fake)
    assert out["status"] == "partial" and out["rounds_executed"] == 1
    assert out["skipped_reason"] == "S1_BELOW_MIN" and out["error_code"] is None
    assert len(out["rounds"]) == 1 and len(fake.calls) == 3
    validate_deliberate_output(out)


@pytest.mark.at("AT-08")
def test_at08_ab():
    fake = Fake(ok_set=["claude"])
    out, _ = run("t", 2, fake)
    assert out["rounds_executed"] == 1
    assert out["skipped_reason"] == "S1_BELOW_MIN"
    assert out["status"] == "partial"
    assert len(fake.calls) == 3  # R1 のみ。R2 呼出は0回
    fake = Fake(ok_set=[])
    out, _ = run("t", 2, fake)
    assert out["status"] == "failed" and out["error_code"] == "ALL_FAILED"
    assert [r["participant"] for r in out["rounds"][0]["results"]] == ORDER
    validate_deliberate_output(out)


@pytest.mark.at("AT-10")
def test_at10_inputs():
    fake = Fake()
    out, _ = run("あ" * 1500, 1, fake)
    assert out["error_code"] is None and out["rounds_requested"] == 1
    fake = Fake()
    out, _ = run("あ" * 1501, 1, fake)
    assert out["error_code"] == "THEME_TOO_LONG" and out["rounds"] == [] and not fake.calls
    for bad in (0, 3, -1, True, "2"):
        fake = Fake()
        out, _ = run("t", bad, fake)
        assert out["error_code"] == "INVALID_INPUT" and out["rounds"] == [] and not fake.calls
    for ok_r in (1, 2):
        out, _ = run("t", ok_r, Fake())
        assert out["error_code"] is None and out["rounds_requested"] == ok_r
    out, _ = run("t", None, Fake())
    assert out["rounds_requested"] == 2
    for blank in ("", "  \n\t"):
        fake = Fake()
        out, _ = run(blank, 1, fake)
        assert out["error_code"] == "INVALID_INPUT" and out["status"] == "failed" and not fake.calls
    validate_deliberate_output(out)


@pytest.mark.at("AT-09")
def test_at09_slots():
    # deliberate は need=3
    p = SlotPool(3)
    fake = Fake(delay=0.01)
    out, _ = run("t", 1, fake, p)
    assert out["error_code"] is None and fake.peak <= 3 and p.running == 0
    for running in (1, 2, 3):
        p = SlotPool(3)
        p.running = running
        fake = Fake()
        out, _ = run("t", 1, fake, p)
        assert out["error_code"] == "BUSY" and out["rounds"] == [] and out["status"] == "failed"
        assert not fake.calls and p.running == running  # 予約は壊れない
    # ask 側 (2,1) 受理 / (3,1) BUSY
    for running, need, want in [(2, 1, True), (3, 1, False)]:
        p = SlotPool(3)
        p.running = running
        assert p.try_reserve(need) is want
        assert p.running == running + (need if want else 0)
    validate_deliberate_output(out)


def test_participant_order_fixed():
    fake = Fake()
    out, _ = run("t", 1, fake)
    assert [r["participant"] for r in out["rounds"][0]["results"]] == ORDER
    assert [c[0] for c in fake.calls] == ORDER
    assert all(fake.reserved_flags)  # 二重取りしない


def test_slot_released_always():
    p = SlotPool(3)
    run("t", 1, Fake(), p)
    assert p.running == 0
    run("t", 2, Fake(ok_set=["claude"]), p)
    assert p.running == 0
    run("t", 2, Fake(ok_set=[]), p)
    assert p.running == 0
    with pytest.raises(RuntimeError):
        run("t", 1, Fake(boom="codex"), p)
    assert p.running == 0
