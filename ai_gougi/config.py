"""既定値表(設計書3)と導出記号。全値は環境変数 AI_GOUGI_<名前> で上書き可。"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from subprocess import list2cmdline

ENV_PREFIX = "AI_GOUGI_"


@dataclass(frozen=True)
class Config:
    WORKDIR: str
    BIN_claude: str = "claude"
    BIN_codex: str = "codex"
    BIN_agy: str = "agy"
    TIMEOUT_SEC: int = 600
    AGY_EMPTY_OUTPUT_RETRIES: int = 2
    AGY_RETRY_DELAY_SEC: int = 1
    KILL_WAIT_SEC: int = 5
    TASKKILL_FLAGS: str = "/T /F"
    CHILD_ENV_EXTRA: str = "PYTHONUTF8=1"
    ENCODING: str = "utf-8"
    PROMPT_MAX_CHARS: int = 7000
    CMDLINE_MAX_CHARS: int = 8000
    AGY_EXE_LEN_REF: int = 38
    CMDLINE_FIXED_CHARS: int = 6
    THEME_MAX_CHARS: int = 1500
    OPINION_MAX_CHARS: int = 2000
    MARKER_FORMAT: str = "\n…[省略 {k} 文字]"
    MARKER_RESERVE: int = 20
    TEMPLATE_MAX_CHARS: int = 500
    OUTPUT_MAX_CHARS: int = 20000
    STDERR_MAX_CHARS: int = 4000
    MIN_SUCCESS_R2: int = 2
    DEFAULT_ROUNDS: int = 2
    MAX_ROUNDS: int = 2
    MAX_CONCURRENT_PROCS: int = 3
    SNAPSHOT_MAX_FILES: int = 5000
    SNAPSHOT_EXCLUDE: tuple = (".git", "node_modules")
    PARTICIPANT_ORDER: tuple = ("claude", "codex", "agy")

    def __post_init__(self):
        for name in ("AGY_EMPTY_OUTPUT_RETRIES", "AGY_RETRY_DELAY_SEC"):
            if getattr(self, name) < 0:
                raise ValueError(f"{ENV_PREFIX}{name} must be >= 0")


def _parse(name: str, default, raw: str):
    if isinstance(default, bool):
        raise TypeError(name)
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError as e:
            raise ValueError(f"{ENV_PREFIX}{name} must be int: {raw!r}") from e
    if isinstance(default, tuple):
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    return raw


def get_config() -> Config:
    """環境変数を毎回読んで Config を返す。整数変換不能なら ValueError。"""
    kwargs = {}
    for f in fields(Config):
        raw = os.environ.get(ENV_PREFIX + f.name)
        if f.name == "WORKDIR":
            kwargs[f.name] = os.path.abspath(raw) if raw is not None else os.path.abspath(os.getcwd())
        elif raw is not None:
            kwargs[f.name] = _parse(f.name, f.default, raw)
    return Config(**kwargs)


def _cfg(cfg):
    return cfg if cfg is not None else get_config()


def period(cfg: Config | None = None) -> int:
    """P = TIMEOUT_SEC + KILL_WAIT_SEC"""
    c = _cfg(cfg)
    return c.TIMEOUT_SEC + c.KILL_WAIT_SEC


def t_max(r: int, cfg: Config | None = None) -> int:
    """T_max(r) = r * P。1 <= r <= MAX_ROUNDS 以外は ValueError。"""
    c = _cfg(cfg)
    if not isinstance(r, int) or r < 1 or r > c.MAX_ROUNDS:
        raise ValueError(f"r must be in 1..{c.MAX_ROUNDS}: {r!r}")
    return r * period(c)


def exe_len(exe: str) -> int:
    """E = len(list2cmdline([exe]))"""
    return len(list2cmdline([exe]))


def base_len(e: int, cfg: Config | None = None) -> int:
    """B = E + CMDLINE_FIXED_CHARS"""
    return e + _cfg(cfg).CMDLINE_FIXED_CHARS


def n_safe(e: int | None = None, cfg: Config | None = None) -> int:
    """N_safe = floor((CMDLINE_MAX_CHARS - B) / 2)"""
    c = _cfg(cfg)
    e = c.AGY_EXE_LEN_REF if e is None else e
    return (c.CMDLINE_MAX_CHARS - base_len(e, c)) // 2


def x_lim(n0: int, e: int | None = None, cfg: Config | None = None) -> int:
    """x_lim(n0) = CMDLINE_MAX_CHARS - B - n0"""
    c = _cfg(cfg)
    e = c.AGY_EXE_LEN_REF if e is None else e
    return c.CMDLINE_MAX_CHARS - base_len(e, c) - n0


def keep(cfg: Config | None = None) -> int:
    """keep = OPINION_MAX_CHARS - MARKER_RESERVE"""
    c = _cfg(cfg)
    return c.OPINION_MAX_CHARS - c.MARKER_RESERVE


def marker_len(k: int, cfg: Config | None = None) -> int:
    """m(k) = len(MARKER_FORMAT.format(k=k))"""
    return len(_cfg(cfg).MARKER_FORMAT.format(k=k))


def w2(cfg: Config | None = None) -> int:
    """W2 = TEMPLATE_MAX_CHARS + THEME_MAX_CHARS + 2*OPINION_MAX_CHARS"""
    c = _cfg(cfg)
    return c.TEMPLATE_MAX_CHARS + c.THEME_MAX_CHARS + 2 * c.OPINION_MAX_CHARS


def return_cap(cfg: Config | None = None) -> int:
    """H = 参加者数 × MAX_ROUNDS × (OUTPUT_MAX_CHARS + STDERR_MAX_CHARS)"""
    c = _cfg(cfg)
    return len(c.PARTICIPANT_ORDER) * c.MAX_ROUNDS * (c.OUTPUT_MAX_CHARS + c.STDERR_MAX_CHARS)
