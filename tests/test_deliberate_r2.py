"""deliberate R2/status を fake run_cli で試験する(実 CLI は呼ばない)。"""
import asyncio

import pytest

from ai_gougi.deliberate import run_deliberate
from ai_gougi.schema import make_ask_result, validate_deliberate_output
from ai_gougi.slots import SlotPool

ORDER = ["claude", "codex", "agy"]


class Fake:
    def __init__(self, ok1=ORDER, ok2=ORDER, boom_r2=None):
        self.ok1, self.ok2, self.boom_r2 = set(ok1), set(ok2), boom_r2
        self.calls = []
        self.seen = {}

    async def __call__(self, participant, prompt, *, pool=None, reserved=False):
        n = self.seen[participant] = self.seen.get(participant, 0) + 1
        self.calls.append((participant, n, prompt))
        await asyncio.sleep(0)
        if n == 2 and self.boom_r2 == participant:
            raise RuntimeError("boom")
        good = participant in (self.ok1 if n == 1 else self.ok2)
        if good:
            return make_ask_result(participant, ok=True, exit_code=0, stdout=f"OP[{participant}]")
        return make_ask_result(participant, ok=False, exit_code=1, error_code="NONZERO_EXIT", error_message="x")


def run(rounds, fake, pool=None):
    pool = pool or SlotPool(3)
    return asyncio.run(run_deliberate("THEME", rounds, fake, pool=pool)), pool


def test_s1_table_r2_counts():
    for s1_set in (ORDER[:2], ORDER):
        fake = Fake(ok1=s1_set)
        out, _ = run(2, fake)
        r2 = [c for c in fake.calls if c[1] == 2]
        assert len(r2) == len(s1_set)
        for p, _n, prompt in r2:
            assert prompt.count("OP[") == len(s1_set) - 1
            assert f"OP[{p}]" not in prompt
        assert out["rounds_executed"] == 2
        validate_deliberate_output(out)
    fake = Fake(ok1=["codex"])
    out, _ = run(2, fake)
    assert out["status"] == "partial" and out["rounds_executed"] == 1
    assert not [c for c in fake.calls if c[1] == 2]
    fake = Fake(ok1=[])
    out, _ = run(2, fake)
    assert out["status"] == "failed" and out["rounds_executed"] == 1
    assert out["status"] != "ok" and not [c for c in fake.calls if c[1] == 2]


def test_status_ok_only_when_all_rounds_all_ok():
    assert run(2, Fake())[0]["status"] == "ok"
    assert run(1, Fake())[0]["status"] == "ok"
    assert run(2, Fake(ok2=["claude", "codex"]))[0]["status"] == "partial"
    assert run(2, Fake(ok1=["claude", "codex"]))[0]["status"] == "partial"
    assert run(1, Fake(ok1=["claude"]))[0]["status"] == "partial"
    assert run(2, Fake(ok1=[]))[0]["status"] == "failed"
    out = run(2, Fake(ok2=[]))[0]
    assert out["status"] == "partial" and out["rounds_executed"] == 2


def test_r2_only_successful_participants():
    fake = Fake(ok1=["claude", "agy"])
    out, _ = run(2, fake)
    r2 = {c[0]: c[2] for c in fake.calls if c[1] == 2}
    assert set(r2) == {"claude", "agy"} and fake.seen["codex"] == 1
    assert "OP[agy]" in r2["claude"] and "OP[claude]" not in r2["claude"]
    assert "OP[claude]" in r2["agy"] and "OP[agy]" not in r2["agy"]
    assert [r["participant"] for r in out["rounds"][1]["results"]] == ["claude", "agy"]


def test_result_order_claude_codex_agy():
    fake = Fake()
    out, _ = run(1, fake)
    assert len(out["rounds"]) == 1 and out["rounds_executed"] == 1
    assert all(c[1] == 1 for c in fake.calls)
    out, _ = run(2, Fake())
    for rd in out["rounds"]:
        assert [r["participant"] for r in rd["results"]] == ORDER


def test_slot_released_after_r2():
    pool = SlotPool(3)
    run(2, Fake(), pool)
    assert pool.running == 0
    with pytest.raises(RuntimeError):
        run(2, Fake(boom_r2="codex"), pool)
    assert pool.running == 0
