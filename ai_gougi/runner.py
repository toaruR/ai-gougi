"""run_cli の起動前段(設計書4,5.3): 検証→枠予約→BIN解決→argv構築。subprocess 起動は後続タスク。

エラー優先順位: INVALID_INPUT -> PROMPT_TOO_LONG -> BUSY -> CLI_NOT_FOUND -> CMDLINE_TOO_LONG
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Optional, Union

from .cmdline import apply_newline, check_cmdline_len
from .config import Config, get_config
from .killtree import kill_tree
from .logging_util import log_decode_replaced
from .schema import AskResult, make_ask_result, make_prelaunch_error
from .slots import SlotPool
from .snapshot import Snapshot, compare_snapshots, take_snapshot
from .truncate import truncate_output, truncate_stderr

POOL = SlotPool()

_PARTICIPANTS = ("claude", "codex", "agy")


@dataclass
class LaunchPlan:
    participant: str
    argv: list
    stdin_text: Optional[str]  # stdin 経路のプロンプト。agy は None
    stdin_devnull: bool  # agy のみ True
    slot_held: bool  # この呼出しが枠を確保している(後続の起動処理が解放する)
    cfg: Config = field(repr=False, default=None)


def _argv_base(participant: str, exe: str, prompt: str) -> tuple[list, Optional[str], bool]:
    if participant == "claude":
        return [exe, "-p", "--permission-mode", "plan"], prompt, False
    if participant == "codex":
        return [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"], prompt, False
    ext = os.path.splitext(exe)[1]
    return [exe, "-p", apply_newline(prompt, ext)], None, True


def prelaunch(
    participant: str,
    prompt: str,
    *,
    pool: SlotPool | None = None,
    reserved: bool = False,
    cfg: Config | None = None,
) -> Union[AskResult, LaunchPlan]:
    """起動前検証。エラーなら AskResult(枠は呼出し前の状態に戻す)、成功なら LaunchPlan。

    reserved=True は deliberate が枠確保済みの場合で、BUSY 判定・予約・解放を行わない。
    """
    c = cfg if cfg is not None else get_config()
    pool = pool if pool is not None else POOL

    if participant not in _PARTICIPANTS:
        return make_prelaunch_error(
            participant, "INVALID_INPUT", f"unknown participant: {participant!r}"
        )
    if not isinstance(prompt, str) or not prompt.strip():
        return make_prelaunch_error(participant, "INVALID_INPUT", "prompt must not be blank")
    if len(prompt) > c.PROMPT_MAX_CHARS:
        return make_prelaunch_error(
            participant,
            "PROMPT_TOO_LONG",
            f"prompt length {len(prompt)} > {c.PROMPT_MAX_CHARS}",
        )

    held = False
    if not reserved:
        if not pool.try_reserve(1):
            return make_prelaunch_error(participant, "BUSY", "all process slots are busy")
        held = True

    def fail(code: str, msg: str) -> AskResult:
        if held:
            pool.release(1)
        return make_prelaunch_error(participant, code, msg)

    bin_name = getattr(c, f"BIN_{participant}")
    found = shutil.which(bin_name)
    if not found:
        return fail("CLI_NOT_FOUND", f"BIN_{participant} not found: {bin_name}")
    exe = os.path.abspath(found)

    argv, stdin_text, devnull = _argv_base(participant, exe, prompt)
    if participant == "agy":
        try:
            check_cmdline_len(exe, prompt, c)
        except ValueError as e:
            return fail("CMDLINE_TOO_LONG", str(e))
    return LaunchPlan(participant, argv, stdin_text, devnull, held, c)


def _child_env(c: Config) -> dict:
    env = dict(os.environ)
    for item in c.CHILD_ENV_EXTRA.split(","):
        k, sep, v = item.strip().partition("=")
        if sep and k:
            env[k] = v
    return env


async def _read_into(stream, buf: bytearray) -> None:
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            return
        buf.extend(chunk)


async def _feed_stdin(proc, data: Optional[bytes]) -> None:
    if proc.stdin is None or data is None:
        return
    try:
        proc.stdin.write(data)
        await proc.stdin.drain()
        proc.stdin.close()  # EOF
    except OSError:
        pass


def _decode(b: bytes, c: Config, who: str) -> str:
    try:
        return b.decode(c.ENCODING)
    except UnicodeDecodeError:
        log_decode_replaced(who)
        return b.decode(c.ENCODING, errors="replace")


def _snapshot(c: Config) -> Snapshot:
    try:
        return take_snapshot(c.WORKDIR, c)
    except (ValueError, OSError):
        return Snapshot(skipped=True)


async def _execute(plan: LaunchPlan) -> AskResult:
    """実行段A+B: 起動・stdin/EOF・TIMEOUT 待機・kill_tree・decode・切詰め・snapshot・ok 判定。"""
    c = plan.cfg
    p = plan.participant
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    before = _snapshot(c)
    try:
        proc = await asyncio.create_subprocess_exec(
            *plan.argv,
            cwd=c.WORKDIR,
            env=_child_env(c),
            stdin=asyncio.subprocess.DEVNULL if plan.stdin_devnull else asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError) as e:
        return make_ask_result(
            p, ok=False, exit_code=None, duration_ms=ms(), workdir_check="skipped",
            error_code="SPAWN_FAILED", error_message=f"{type(e).__name__}: {e}",
        )

    out_buf, err_buf = bytearray(), bytearray()
    data = plan.stdin_text.encode(c.ENCODING) if plan.stdin_text is not None else None
    all_t = [
        asyncio.ensure_future(_feed_stdin(proc, data)),
        asyncio.ensure_future(_read_into(proc.stdout, out_buf)),
        asyncio.ensure_future(_read_into(proc.stderr, err_buf)),
        asyncio.ensure_future(proc.wait()),
    ]

    # 部分出力を保持するため communicate() ではなく自前 reader + asyncio.wait(timeout)
    _, pending = await asyncio.wait(all_t, timeout=c.TIMEOUT_SEC)
    timed_out = bool(pending)
    if timed_out:
        await kill_tree(proc, c)
        # kill 後、パイプ閉鎖(読取完了)を KILL_WAIT_SEC まで待つ。部分出力は保持。
        rest = [t for t in all_t if not t.done()]
        if rest:
            _, pending = await asyncio.wait(rest, timeout=c.KILL_WAIT_SEC)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.wait(pending, timeout=1)
    for t in all_t:
        if t.done() and not t.cancelled():
            t.exception()  # 未取得例外の警告抑止

    stdout = _decode(bytes(out_buf), c, f"{p} stdout")
    stderr = _decode(bytes(err_buf), c, f"{p} stderr")
    stdout_t, out_total, out_trunc = truncate_output(stdout, c)
    stderr_t, err_total, err_trunc = truncate_stderr(stderr, c)

    code = proc.returncode
    wcheck = compare_snapshots(before, _snapshot(c))

    ok = (not timed_out) and code == 0 and bool(stdout.strip())
    error_code = error_message = None
    if timed_out:
        error_code, error_message = "TIMEOUT", f"timed out after {c.TIMEOUT_SEC}s"
    elif code != 0:
        error_code, error_message = "NONZERO_EXIT", f"exit code {code}"
    elif not ok:
        error_code, error_message = "EMPTY_OUTPUT", "stdout is empty"
    return make_ask_result(
        p, ok=ok, exit_code=code, stdout=stdout_t, stderr=stderr_t,
        stdout_total_chars=out_total, stderr_total_chars=err_total,
        stdout_truncated=out_trunc, stderr_truncated=err_trunc,
        timed_out=timed_out, duration_ms=ms(), workdir_check=wcheck,
        error_code=error_code, error_message=error_message,
    )


async def run_cli(
    participant: str,
    prompt: str,
    *,
    pool: SlotPool | None = None,
    reserved: bool = False,
) -> AskResult:
    """起動前段 + 実行段A。枠は全経路で解放する。"""
    plan = prelaunch(participant, prompt, pool=pool, reserved=reserved)
    if not isinstance(plan, LaunchPlan):
        return plan
    try:
        return await _execute(plan)
    finally:
        if plan.slot_held:
            (pool if pool is not None else POOL).release(1)


