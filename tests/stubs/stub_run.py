"""stub CLI で run_cli を1回実行し結果JSONを stdout に出す。ok なら終了コード0、他は1。

使用法: stub_run.py PARTICIPANT MODE [--prompt-len N] [--quote-count Q] [--timeout S] [--kill-wait S]
        stub_run.py --deliberate MODE [--timeout S] [--kill-wait S]   (3者とも同MODEの stub で run_deliberate を1回実行。status=='ok' なら0)
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


AGY_ECHO = (
    "import sys\n"
    "a = sys.argv[1:]\n"
    "sys.stdout.buffer.write(a[a.index('-p') + 1].encode('utf-8'))\n"
)


def install_deliberate_stubs(td, modes: dict) -> dict:
    """participant->mode の辞書で .cmd shim を生成し AI_GOUGI_BIN_* を返す。

    mode は shim 内で強制設定する(環境の STUB_MODE に依存しない)。
    agy は stdin を使わない(argv -p)ため、echo_stdin 相当は argv を echo する専用 shim。
    modes に無い参加者は生成しない(呼出側が別途パスを設定する)。
    """
    d = Path(td)
    d.mkdir(parents=True, exist_ok=True)
    env = {}
    for name, mode in modes.items():
        p = d / f"{name}.cmd"
        if name == "agy" and mode == "echo_stdin":
            py = d / "agy_echo.py"
            py.write_text(AGY_ECHO, encoding="utf-8")
            pre = ""
            run_line = f'"{sys.executable}" "{py}" %*\r\n'
        else:
            pre = f'set "STUB_MODE={mode}"\r\n'
            run_line = f'"{sys.executable}" "{STUB_CLI}" %*\r\n'
        p.write_text("@echo off\r\n" + pre + run_line + "exit /b %ERRORLEVEL%\r\n", encoding="ascii")
        env[f"AI_GOUGI_BIN_{name}"] = str(p.resolve())
    return env


def deliberate_main(mode: str, timeout=None, kill_wait=None) -> int:
    if timeout is not None:
        os.environ["AI_GOUGI_TIMEOUT_SEC"] = str(timeout)
    if kill_wait is not None:
        os.environ["AI_GOUGI_KILL_WAIT_SEC"] = str(kill_wait)
    with tempfile.TemporaryDirectory() as td:
        for k, v in install_deliberate_stubs(td, {n: mode for n in NAMES}).items():
            os.environ[k] = v
        from ai_gougi.deliberate import run_deliberate
        from ai_gougi.slots import SlotPool

        out = asyncio.run(run_deliberate("stub deliberate theme", 2, pool=SlotPool(3)))
    sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0 if out["status"] == "ok" else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--deliberate":
        dp = argparse.ArgumentParser(prog="stub_run.py --deliberate")
        dp.add_argument("mode")
        dp.add_argument("--timeout", type=int, default=None)
        dp.add_argument("--kill-wait", type=int, default=None)
        try:
            da = dp.parse_args(argv[1:])
        except SystemExit:
            return 2
        return deliberate_main(da.mode, da.timeout, da.kill_wait)
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
