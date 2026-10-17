"""agy の一時的な空出力、再試行上限、共有時間予算を検証する。"""
import asyncio
import sys

import anyio
import pytest

from ai_gougi import runner
from ai_gougi.config import get_config
from ai_gougi.schema import make_ask_result, validate_ask_result, validate_deliberate_output
from ai_gougi.slots import SlotPool
from ai_gougi.snapshot import Snapshot
from tests import smoke_mcp
from tests.test_runner_agy import _shim


@pytest.fixture
def retry_env(tmp_path, monkeypatch):
    for name in ("agy", "claude", "codex"):
        monkeypatch.setenv(f"AI_GOUGI_BIN_{name}", sys.executable)
    monkeypatch.setenv("AI_GOUGI_WORKDIR", str(tmp_path))
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "10")
    monkeypatch.setenv("AI_GOUGI_AGY_EMPTY_OUTPUT_RETRIES", "2")
    monkeypatch.setenv("AI_GOUGI_AGY_RETRY_DELAY_SEC", "1")
    clock = [100.0]
    sleeps = []
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(runner.asyncio, "sleep", sleep)
    return clock, sleeps


def reply(code=None, *, check="unchanged"):
    return make_ask_result(
        "agy", ok=code is None, exit_code=0 if code in (None, "EMPTY_OUTPUT") else 1,
        stdout="answer" if code is None else "", stderr="diagnostic",
        workdir_check=check, timed_out=code == "TIMEOUT", error_code=code,
        error_message="stdout is empty" if code else None)


def execute_sequence(monkeypatch, replies, pool, *, reserved=False):
    seen = []

    async def execute(plan, *, timeout=None):
        assert pool.running == (3 if reserved else 1)
        seen.append((plan.argv[:], timeout))
        return replies.pop(0)

    monkeypatch.setattr(runner, "_execute", execute)
    return seen


def test_empty_then_success_preserves_slot_prompt_and_total_duration(retry_env, monkeypatch, capsys):
    _, sleeps = retry_env
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT"), reply("EMPTY_OUTPUT"), reply()], pool)
    result = asyncio.run(runner.run_cli("agy", "private prompt", pool=pool))
    validate_ask_result(result)
    assert result["ok"] and result["stdout"] == "answer"
    assert result["duration_ms"] == 3000 and sleeps == [1, 2]
    assert [t for _, t in seen] == [10, 9, 7]
    assert all(argv == seen[0][0] for argv, _ in seen)
    assert pool.running == 0
    out, err = capsys.readouterr()
    assert out == "" and "private prompt" not in err and "diagnostic" not in err
    assert "attempts=3 ok=True" in err


def test_persistent_empty_stops_at_limit(retry_env, monkeypatch):
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT") for _ in range(3)], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    validate_ask_result(result)
    assert len(seen) == 3 and pool.running == 0
    assert result["error_code"] == "EMPTY_OUTPUT" and result["stderr"] == "diagnostic"
    assert "after 3 attempts" in result["error_message"]


@pytest.mark.parametrize("code", [None, "TIMEOUT", "NONZERO_EXIT", "SPAWN_FAILED"])
def test_other_results_not_retried(retry_env, monkeypatch, code):
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply(code)], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert len(seen) == 1 and result["error_code"] == code and pool.running == 0
    assert retry_env[1] == []


@pytest.mark.parametrize("participant", ["claude", "codex"])
def test_other_participants_not_retried(retry_env, monkeypatch, participant):
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT")], pool)
    asyncio.run(runner.run_cli(participant, "q", pool=pool))
    assert len(seen) == 1 and retry_env[1] == [] and pool.running == 0


def test_retry_can_be_disabled(retry_env, monkeypatch):
    monkeypatch.setenv("AI_GOUGI_AGY_EMPTY_OUTPUT_RETRIES", "0")
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT")], pool)
    asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert len(seen) == 1 and retry_env[1] == []


def test_error_after_empty_stops_retrying(retry_env, monkeypatch):
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT"), reply("NONZERO_EXIT")], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert result["error_code"] == "NONZERO_EXIT" and result["stderr"] == "diagnostic"
    assert len(seen) == 2 and retry_env[1] == [1] and pool.running == 0


def test_execution_time_is_deducted_from_retry_budget(retry_env, monkeypatch):
    clock, _ = retry_env
    pool = SlotPool(3)
    timeouts = []

    async def execute(plan, *, timeout=None):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            clock[0] += 8.5
            return reply("EMPTY_OUTPUT")
        clock[0] += timeout
        return reply("TIMEOUT")

    monkeypatch.setattr(runner, "_execute", execute)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert timeouts == [10, 0.5] and result["timed_out"]
    assert result["duration_ms"] == 10000 and pool.running == 0


def test_snapshot_and_spawn_time_are_deducted_from_wait(retry_env, monkeypatch):
    clock, _ = retry_env
    timeouts = []

    class Stream:
        def __init__(self, data):
            self.data = data

        async def read(self, size):
            data, self.data = self.data, b""
            return data

    class Process:
        stdin = None
        stdout = Stream(b"ok")
        stderr = Stream(b"")
        returncode = 0

        async def wait(self):
            return 0

    def snapshot(cfg):
        clock[0] += 2
        return Snapshot()

    async def spawn(*args, **kwargs):
        clock[0] += 1
        return Process()

    async def wait(tasks, *, timeout):
        timeouts.append(timeout)
        await asyncio.gather(*tasks)
        return set(tasks), set()

    monkeypatch.setattr(runner, "_snapshot", snapshot)
    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(runner.asyncio, "wait", wait)
    plan = runner.prelaunch("agy", "q", reserved=True)
    result = asyncio.run(runner._execute(plan, timeout=10))
    assert result["ok"] and timeouts == [7]


def test_insufficient_budget_does_not_sleep_or_spawn(retry_env, monkeypatch):
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "1")
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT")], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert result["error_code"] == "EMPTY_OUTPUT" and len(seen) == 1
    assert retry_env[1] == [] and pool.running == 0


def test_budget_expires_during_backoff(retry_env, monkeypatch):
    clock, _ = retry_env

    async def oversleep(delay):
        clock[0] += 20

    monkeypatch.setattr(runner.asyncio, "sleep", oversleep)
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT")], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert len(seen) == 1 and pool.running == 0
    assert "budget exhausted" in result["error_message"]
    assert result["duration_ms"] == 20000


@pytest.mark.parametrize("checks,expected", [
    (["changed", "unchanged"], "changed"), (["skipped", "unchanged"], "skipped"),
    (["changed", "skipped"], "changed"),
])
def test_workdir_changes_from_previous_attempt_survive(retry_env, monkeypatch, checks, expected):
    pool = SlotPool(3)
    execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT", check=checks[0]), reply(check=checks[1])], pool)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert result["ok"] and result["workdir_check"] == expected


def test_reserved_slot_not_reserved_or_released_again(retry_env, monkeypatch):
    pool = SlotPool(3)
    assert pool.try_reserve(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT"), reply()], pool, reserved=True)
    result = asyncio.run(runner.run_cli("agy", "q", pool=pool, reserved=True))
    assert result["ok"] and len(seen) == 2 and pool.running == 3
    pool.release(3)


def test_cancel_during_backoff_releases_slot(retry_env, monkeypatch):
    async def cancelled(delay):
        raise asyncio.CancelledError()

    monkeypatch.setattr(runner.asyncio, "sleep", cancelled)
    pool = SlotPool(3)
    seen = execute_sequence(monkeypatch, [reply("EMPTY_OUTPUT")], pool)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner.run_cli("agy", "q", pool=pool))
    assert len(seen) == 1 and pool.running == 0


@pytest.mark.parametrize("name", ["AGY_EMPTY_OUTPUT_RETRIES", "AGY_RETRY_DELAY_SEC"])
def test_invalid_retry_settings_rejected(monkeypatch, name):
    monkeypatch.setenv("AI_GOUGI_" + name, "-1")
    with pytest.raises(ValueError, match=name):
        get_config()


# stdout が空白→空→回答になる実プロセス。カウンタは WORKDIR 外に置く。
FLAKY = '''import pathlib,sys
counter = pathlib.Path(__file__).with_suffix('.count')
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
sys.stderr.write('attempt=' + str(n))
if n == 1:
    sys.stdout.write(' \\n\\t')
elif n >= 3:
    print('recovered answer')
'''


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only: real .cmd shim")
@pytest.mark.parametrize("tool", ["ask_agy", "deliberate"])
def test_stdio_mcp_recovers_from_empty_output(tmp_path, tool):
    shim = _shim(tmp_path / "flaky", FLAKY)
    params = smoke_mcp.stdio_params(
        tmp_path / "server", {n: "echo_stdin" for n in ("claude", "codex", "agy")},
        {"AI_GOUGI_BIN_agy": str(shim), "AI_GOUGI_AGY_RETRY_DELAY_SEC": "0",
         "AI_GOUGI_AGY_EMPTY_OUTPUT_RETRIES": "2"})
    args = {"prompt": "question"} if tool == "ask_agy" else {"theme": "question", "rounds": 2}
    result = anyio.run(smoke_mcp.stdio_session_call, params, [(tool, args)])[0]
    assert not result.isError
    sc = result.structuredContent
    if tool == "ask_agy":
        validate_ask_result(sc)
        assert sc["ok"] and sc["stdout"].strip() == "recovered answer"
        assert sc["stderr"] == "attempt=3"
    else:
        validate_deliberate_output(sc)
        assert sc["status"] == "ok" and sc["rounds_executed"] == 2
        assert all(r["ok"] for round_ in sc["rounds"] for r in round_["results"])
    counter = tmp_path / "flaky" / "agy_s.count"
    assert counter.read_text() == ("3" if tool == "ask_agy" else "4")
