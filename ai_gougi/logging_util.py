"""log 系防御の stderr 1行記録(stdout は MCP stdio 用なので使わない)。"""
from __future__ import annotations

import os
import sys

from .config import Config, get_config

KINDS = ("decode_replaced", "newline_replaced", "nongit_workdir", "startup_env")


def log_event(kind: str, msg: str) -> None:
    """stderr に改行1つで終わる1行を書く。未知の kind は ValueError。"""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    line = " ".join(str(msg).splitlines()) if msg else ""
    sys.stderr.write(f"[ai_gougi] {kind}: {line}\n")
    sys.stderr.flush()


def log_startup_env(cfg: Config | None = None) -> None:
    c = cfg if cfg is not None else get_config()
    extra = c.CHILD_ENV_EXTRA
    if extra.strip():
        log_event("startup_env", f"CHILD_ENV_EXTRA={extra}")
    else:
        log_event("startup_env", "CHILD_ENV_EXTRA 無効(空文字上書き)")


def is_git_repo(path: str) -> bool:
    """path 自身または祖先に .git があれば True。"""
    cur = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def log_nongit_workdir(path: str) -> None:
    log_event("nongit_workdir", f"git管理外 WORKDIR: {path} (codex は --skip-git-repo-check で起動)")


def log_decode_replaced(who: str = "") -> None:
    log_event("decode_replaced", f"出力の不正バイトを置換(errors=replace) {who}".rstrip())


def log_newline_replaced(who: str = "") -> None:
    log_event("newline_replaced", f".cmd 実行のため改行を置換 {who}".rstrip())
