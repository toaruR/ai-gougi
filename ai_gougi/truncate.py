"""切り詰め(設計書 (C)(E))。戻り値は (text, total_chars, truncated)。"""
from __future__ import annotations

from .config import Config, get_config, keep as _keep


def _check(text):
    if not isinstance(text, str):
        raise TypeError(f"text must be str: {type(text).__name__}")


def truncate_opinion(text: str, cfg: Config | None = None) -> tuple[str, int, bool]:
    """len<=OPINION_MAX_CHARS は原文。超過時は先頭 keep 字 + マーカー(k=len-keep)。"""
    _check(text)
    c = cfg if cfg is not None else get_config()
    n = len(text)
    if n <= c.OPINION_MAX_CHARS:
        return text, n, False
    kp = _keep(c)
    return text[:kp] + c.MARKER_FORMAT.format(k=n - kp), n, True


def truncate_output(stdout: str, cfg: Config | None = None) -> tuple[str, int, bool]:
    """先頭 OUTPUT_MAX_CHARS 字を残す。"""
    _check(stdout)
    c = cfg if cfg is not None else get_config()
    n = len(stdout)
    if n <= c.OUTPUT_MAX_CHARS:
        return stdout, n, False
    return stdout[: c.OUTPUT_MAX_CHARS], n, True


def truncate_stderr(stderr: str, cfg: Config | None = None) -> tuple[str, int, bool]:
    """末尾 STDERR_MAX_CHARS 字を残す。"""
    _check(stderr)
    c = cfg if cfg is not None else get_config()
    n = len(stderr)
    if n <= c.STDERR_MAX_CHARS:
        return stderr, n, False
    return stderr[n - c.STDERR_MAX_CHARS:], n, True
