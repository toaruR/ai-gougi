"""Windows コマンドライン長の検査(設計書4.1 B1/B2)と拡張子別の改行規則。純粋関数のみ。"""
from __future__ import annotations

import os
import shutil
from subprocess import list2cmdline

from .config import Config, base_len, exe_len, get_config, n_safe, x_lim

__all__ = [
    "exe_len", "base_len", "n_safe", "x_lim", "newline_policy", "apply_newline",
    "measure_len", "resolve_exe_len", "check_cmdline_len",
]


def newline_policy(ext: str) -> str:
    """'.cmd' -> 'escape'(LF を2字の \\n へ), それ以外('.exe' 等) -> 'keep'。大文字小文字無視。"""
    return "escape" if (ext or "").lower() == ".cmd" else "keep"


def _ext(exe: str) -> str:
    return os.path.splitext(exe)[1].lower()


def apply_newline(prompt: str, ext: str) -> str:
    if newline_policy(ext) == "escape":
        return prompt.replace("\n", "\\n")
    return prompt


def measure_len(exe: str, prompt: str) -> int:
    """実測 L = len(list2cmdline([exe,'-p',prompt_after_newline_policy]))"""
    return len(list2cmdline([exe, "-p", apply_newline(prompt, _ext(exe))]))


def resolve_exe_len(name: str) -> int:
    """which 解決後の実パスから E を実測する。解決不能なら name 自体で実測。"""
    return exe_len(shutil.which(name) or name)


def check_cmdline_len(exe: str, prompt: str, cfg: Config | None = None) -> None:
    """L > CMDLINE_MAX_CHARS なら ValueError('CMDLINE_TOO_LONG ...')。E は exe の実測で、定数参照値は使わない。"""
    c = cfg if cfg is not None else get_config()
    length = measure_len(exe, prompt)
    if length > c.CMDLINE_MAX_CHARS:
        raise ValueError(f"CMDLINE_TOO_LONG: L={length} > {c.CMDLINE_MAX_CHARS}")
    return None
