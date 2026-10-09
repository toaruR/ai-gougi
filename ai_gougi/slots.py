"""(G) 並列枠予約。try_reserve は await を挟まず検査と予約を行う(キュー待ちなし)。"""
from __future__ import annotations

from contextlib import contextmanager

from ai_gougi.config import get_config

BUSY = "BUSY"


class SlotPool:
    def __init__(self, max: int | None = None):
        self.max = get_config().MAX_CONCURRENT_PROCS if max is None else max
        self.running = 0

    def try_reserve(self, need: int) -> bool:
        """running+need <= max なら予約して True。不一致は False(BUSY)。"""
        if need < 1 or self.running + need > self.max:
            return False
        self.running += need
        return True

    def release(self, n: int) -> None:
        if n < 0 or n > self.running:
            raise ValueError(f"release({n}) exceeds running={self.running}")
        self.running -= n

    @contextmanager
    def reserved(self, need: int):
        """受理時のみ解放を保証する。yield 値は受理(True)/BUSY(False)。"""
        ok = self.try_reserve(need)
        try:
            yield ok
        finally:
            if ok:
                self.release(need)
