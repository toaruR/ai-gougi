"""stub CLI で run_cli を1回実行し結果JSONを stdout に出す。ok なら終了コード0、他は1。

使用法: stub_run.py PARTICIPANT MODE [--prompt-len N] [--quote-count Q] [--timeout S] [--kill-wait S]
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_stubs import NAMES, STUB_CLI, install_stubs  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser()
    ap.add_argument("participant", choices=["claude", "codex", "agy"])
    ap.add_argument("mode")
    ap.add_argument("--prompt-len", type=int, default=5)
    ap.add_argument("--quote-count", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--kill-wait", type=int, default=None)
    a = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as td:
        for k, v in install_stubs(td, a.mode).items():
            os.environ[k] = v
        os.environ["STUB_MODE"] = a.mode
        if a.timeout is not None:
            os.environ["AI_GOUGI_TIMEOUT_SEC"] = str(a.timeout)
        if a.kill_wait is not None:
            os.environ["AI_GOUGI_KILL_WAIT_SEC"] = str(a.kill_wait)
        from ai_gougi.runner import run_cli
        from ai_gougi.slots import SlotPool

        prompt = "a" * max(a.prompt_len - a.quote_count, 1) + '"' * a.quote_count
        r = asyncio.run(run_cli(a.participant, prompt, pool=SlotPool(3)))
    sys.stdout.buffer.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
