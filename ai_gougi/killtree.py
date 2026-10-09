"""Windows taskkill によるプロセスツリー kill と KILL_WAIT_SEC 回収。"""
from __future__ import annotations

import asyncio
import subprocess

from .config import Config, get_config

LAUNCH_FAILED = 127


def build_argv(pid: int, flags: str) -> list[str]:
    return ["taskkill", "/PID", str(pid), *flags.split()]


def run_taskkill(pid: int, flags: str) -> int:
    """taskkill の終了コード。起動不能(taskkill 不在等)は非0(127)。"""
    try:
        r = subprocess.run(build_argv(pid, flags), capture_output=True, stdin=subprocess.DEVNULL)
    except (OSError, ValueError):
        return LAUNCH_FAILED
    return r.returncode


async def kill_tree(proc, cfg: Config | None = None) -> bool:
    """TASKKILL_FLAGS でツリーを kill し KILL_WAIT_SEC 以内に回収できれば True。
    回収不能なら False を返して放置する(F28 not guarded)。例外は送出しない。"""
    try:
        c = cfg if cfg is not None else get_config()
        await asyncio.to_thread(run_taskkill, proc.pid, c.TASKKILL_FLAGS)
        await asyncio.wait_for(proc.wait(), c.KILL_WAIT_SEC)
        return True
    except Exception:
        return False
