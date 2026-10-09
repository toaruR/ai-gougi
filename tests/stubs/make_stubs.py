"""一時ディレクトリに stub CLI(.cmd shim)を生成し AI_GOUGI_BIN_* の辞書を返す。"""
import sys
from pathlib import Path

STUB_CLI = Path(__file__).with_name("stub_cli.py").resolve()
NAMES = ("claude", "codex", "agy")


def install_stubs(tmp_dir, mode: str = "echo_stdin") -> dict:
    """claude.cmd/codex.cmd/agy.cmd を生成し {'AI_GOUGI_BIN_<name>': 絶対パス} を返す。

    mode は STUB_MODE が未設定のときの既定。呼出側が STUB_MODE を設定すれば優先。
    agy.exe 相当は python.exe に argv を解釈させられないため実 spawn せず、
    拡張子切替は argv 構築層で検証する(ここでは agy.cmd のみ生成)。
    """
    d = Path(tmp_dir)
    d.mkdir(parents=True, exist_ok=True)
    env = {}
    for name in NAMES:
        p = d / f"{name}.cmd"
        p.write_text(
            "@echo off\r\n"
            f'if not defined STUB_MODE set "STUB_MODE={mode}"\r\n'
            f'"{sys.executable}" "{STUB_CLI}" %*\r\n'
            "exit /b %ERRORLEVEL%\r\n",
            encoding="ascii",
        )
        env[f"AI_GOUGI_BIN_{name}"] = str(p.resolve())
    return env


def apply_env(monkeypatch, tmp_dir, mode: str = "echo_stdin") -> dict:
    env = install_stubs(tmp_dir, mode)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env
