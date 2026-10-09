"""合議ステートマシン(設計書6)(入力検証・枠予約・R1・R2・status判定)。"""
from __future__ import annotations

import asyncio
import time

from .config import get_config
from .prompts import build_r1_prompt, build_r2_prompt
from .runner import POOL, run_cli
from .schema import DeliberateOutput
from .slots import SlotPool


def _out(status, error_code, error_message, requested, executed, skipped, t0, rounds) -> DeliberateOutput:
    return {
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "rounds_requested": requested,
        "rounds_executed": executed,
        "skipped_reason": skipped,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
        "rounds": rounds,
    }  # type: ignore[return-value]


async def _run_round(run_cli_fn, order, prompts, pool):
    """参加者を並列実行し PARTICIPANT_ORDER 順の結果を返す。例外は全完了後に再送出。"""
    tasks = [run_cli_fn(p, prompts[p], pool=pool, reserved=True) for p in order]
    got = await asyncio.gather(*tasks, return_exceptions=True)
    for g in got:
        if isinstance(g, BaseException):
            raise g
    return list(got)


async def run_deliberate(
    theme, rounds, run_cli_fn=run_cli, *, pool: SlotPool | None = None
) -> DeliberateOutput:
    t0 = time.monotonic()
    c = get_config()
    pool = pool if pool is not None else POOL
    requested = c.DEFAULT_ROUNDS if rounds is None else rounds

    def fail(code, msg):
        return _out("failed", code, msg, requested if isinstance(requested, int) else 0, 0, None, t0, [])

    if not isinstance(theme, str) or not theme.strip():
        return fail("INVALID_INPUT", "theme must not be blank")
    if (
        not isinstance(requested, int)
        or isinstance(requested, bool)
        or requested < 1
        or requested > c.MAX_ROUNDS
    ):
        return fail("INVALID_INPUT", f"rounds must be in 1..{c.MAX_ROUNDS}: {rounds!r}")
    if len(theme) > c.THEME_MAX_CHARS:
        return fail("THEME_TOO_LONG", f"theme length {len(theme)} > {c.THEME_MAX_CHARS}")

    order = tuple(c.PARTICIPANT_ORDER)
    need = len(order)
    with pool.reserved(need) as ok:
        if not ok:
            return fail("BUSY", "all process slots are busy")
        prompt = build_r1_prompt(theme)
        r1 = await _run_round(run_cli_fn, order, {p: prompt for p in order}, pool)
        rounds_out = [{"round": 1, "results": r1}]
        s1 = sum(1 for r in r1 if r["ok"])
        if s1 == 0:
            return _out("failed", "ALL_FAILED", "all participants failed in round 1",
                        requested, 1, None, t0, rounds_out)
        if s1 < c.MIN_SUCCESS_R2 and requested >= 2:
            return _out("partial", None, None, requested, 1, "S1_BELOW_MIN", t0, rounds_out)
        # 暫定: R2 未実装。S1>=MIN_SUCCESS_R2 は R1 結果のみ返す(後続タスクで置換)
        all_ok = s1 == need
        status = "ok" if requested == 1 and all_ok else "partial"
        return _out(status, None, None, requested, 1, None, t0, rounds_out)
