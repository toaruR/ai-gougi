"""WORKDIR 書込検知(検知のみ・予防はしない)。changed/unchanged/skipped。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .config import Config, _cfg


@dataclass(frozen=True)
class Snapshot:
    files: dict = field(default_factory=dict)  # 相対パス -> (mtime_ns, size)
    skipped: bool = False


def take_snapshot(root, cfg: Config | None = None) -> Snapshot:
    """root が存在するディレクトリでなければ ValueError。上限超過で skipped。"""
    root = os.fspath(root)
    if not os.path.isdir(root):
        raise ValueError(f"root is not an existing directory: {root!r}")
    c = _cfg(cfg)
    exclude = set(c.SNAPSHOT_EXCLUDE)
    files: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for name in filenames:
            if len(files) >= c.SNAPSHOT_MAX_FILES:
                return Snapshot(skipped=True)
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files[os.path.relpath(p, root).replace(os.sep, "/")] = (st.st_mtime_ns, st.st_size)
    return Snapshot(files=files)


def compare_snapshots(before: Snapshot, after: Snapshot) -> str:
    """'skipped' / 'changed' / 'unchanged'"""
    if before.skipped or after.skipped:
        return "skipped"
    return "unchanged" if before.files == after.files else "changed"
