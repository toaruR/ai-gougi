import os

import pytest

from ai_gougi.config import get_config
from ai_gougi.snapshot import compare_snapshots, take_snapshot


def test_changed_unchanged(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    s1 = take_snapshot(tmp_path)
    assert compare_snapshots(s1, take_snapshot(tmp_path)) == "unchanged"
    (tmp_path / "b.txt").write_text("b")
    assert compare_snapshots(s1, take_snapshot(tmp_path)) == "changed"


def test_skipped_over_max_files(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_GOUGI_SNAPSHOT_MAX_FILES", "3")
    for i in range(get_config().SNAPSHOT_MAX_FILES + 1):
        (tmp_path / f"f{i}.txt").write_text("x")
    s = take_snapshot(tmp_path)
    assert s.skipped
    assert compare_snapshots(s, take_snapshot(tmp_path)) == "skipped"


def test_excludes_ignored(tmp_path):
    for d in (".git", "node_modules"):
        (tmp_path / d).mkdir()
    s1 = take_snapshot(tmp_path)
    (tmp_path / ".git" / "x").write_text("1")
    (tmp_path / "node_modules" / "y").write_text("1")
    assert compare_snapshots(s1, take_snapshot(tmp_path)) == "unchanged"


def test_delete_modify_changed(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("abc")
    s1 = take_snapshot(tmp_path)
    f.write_text("abcdef")
    s2 = take_snapshot(tmp_path)
    assert compare_snapshots(s1, s2) == "changed"
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert compare_snapshots(s2, take_snapshot(tmp_path)) == "changed"
    f.unlink()
    assert compare_snapshots(s2, take_snapshot(tmp_path)) == "changed"


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(ValueError):
        take_snapshot(tmp_path / "nope")
    (tmp_path / "f").write_text("x")
    with pytest.raises(ValueError):
        take_snapshot(tmp_path / "f")
