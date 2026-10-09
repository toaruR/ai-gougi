import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_task_commit as ctc  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_task_commit.py"
OK_TEST = "def test_ok():\n    assert True\n"


def _init(repo):
    ctc._git(repo, "init", "-q", check=True)


def test_has_task_commit_matches_prefix_only(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: a", {"a.txt": "1\n"})
    assert ctc.has_task_commit(tmp_path, "T001")
    for i, s in enumerate(["xT001: a", "T0011: a", "T001 a"]):
        repo = tmp_path / f"r{i}"
        repo.mkdir()
        _init(repo)
        ctc._commit(repo, s, {"a.txt": "1\n"})
        assert not ctc.has_task_commit(repo, "T001")


def test_has_task_commit_missing_returns_false(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: a", {"a.txt": "1\n"})
    assert ctc.has_task_commit(tmp_path, "T999") is False


def test_suite_green_detects_failure(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: ok", {"test_ok.py": OK_TEST})
    assert ctc.suite_green(tmp_path) is True
    ctc._commit(tmp_path, "T002: bad", {"test_bad.py": "def test_bad():\n    assert False\n"})
    assert ctc.suite_green(tmp_path) is False


def test_revert_check_leaf_green(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: ok", {"test_ok.py": OK_TEST})
    ctc._commit(tmp_path, "T002: leaf", {"b.txt": "x\n"})
    assert ctc.revert_check(tmp_path, "T002") is True
    assert "revchk_" not in ctc._git(tmp_path, "worktree", "list").stdout


def test_revert_check_conflict_red(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: ok", {"test_ok.py": OK_TEST, "v.txt": "0\n"})
    ctc._commit(tmp_path, "T002: v1", {"v.txt": "1\n"})
    ctc._commit(tmp_path, "T003: v2", {"v.txt": "2\n"})
    assert ctc.revert_check(tmp_path, "T002") is False


def test_cli_unknown_task_exit1(tmp_path):
    _init(tmp_path)
    ctc._commit(tmp_path, "T001: a", {"a.txt": "1\n"})
    r = subprocess.run([sys.executable, str(SCRIPT), "T999", "--repo", str(tmp_path)])
    assert r.returncode == 1


def test_cli_usage_error_exit2(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "nope", "--repo", str(tmp_path)])
    assert r.returncode == 2


def test_self_test_exit0():
    r = subprocess.run([sys.executable, str(SCRIPT), "--self-test"])
    assert r.returncode == 0
