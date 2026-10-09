"""Task commit / rollback boundary checker (stdlib only).

Usage:
  check_task_commit.py T0xx [--green] [--revert-check] [--with-dependents] [--repo PATH]
  check_task_commit.py --self-test
Exit: 0 ok, 1 check failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_IDENT = ["-c", "user.name=check", "-c", "user.email=check@example.invalid"]


def _git(repo, *args, check=False):
    return subprocess.run(
        ["git", *_IDENT, *args], cwd=str(repo), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=check,
    )


def _subjects(repo):
    """Return list of (sha, subject), newest first."""
    r = _git(repo, "log", "--format=%H%x09%s")
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        sha, _, subj = line.partition("\t")
        out.append((sha, subj))
    return out


def find_task_commit(repo, task):
    """SHA of the newest commit whose subject starts with 'task:' or None."""
    prefix = f"{task}:"
    for sha, subj in _subjects(repo):
        if subj.startswith(prefix):
            return sha
    return None


def has_task_commit(repo, task) -> bool:
    return find_task_commit(repo, task) is not None


def suite_green(repo) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(repo),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0


def revert_point(repo, task):
    sha = find_task_commit(repo, task)
    if sha is None:
        return None
    r = _git(repo, "rev-parse", f"{sha}^")
    return r.stdout.strip() if r.returncode == 0 else None


def _dependents(repo, task):
    """Later task commits with a higher numeric id, highest id first."""
    m = re.fullmatch(r"T(\d+)", task)
    base = int(m.group(1)) if m else 0
    found = {}
    for sha, subj in _subjects(repo):
        mm = re.match(r"T(\d+):", subj)
        if mm and int(mm.group(1)) > base:
            found.setdefault(int(mm.group(1)), sha)
    return [found[k] for k in sorted(found, reverse=True)]


def revert_check(repo, task, with_dependents=False, out=None) -> bool:
    out = out or sys.stdout
    sha = find_task_commit(repo, task)
    if sha is None:
        return False
    point = revert_point(repo, task)
    print(f"revert point: {point or '(root commit, none)'}", file=out)
    to_revert = (_dependents(repo, task) if with_dependents else []) + [sha]
    tmp = Path(tempfile.mkdtemp(prefix="revchk_"))
    wt = tmp / "wt"
    try:
        if _git(repo, "worktree", "add", "--detach", str(wt), "HEAD").returncode != 0:
            return False
        for c in to_revert:
            if _git(wt, "revert", "--no-edit", c).returncode != 0:
                _git(wt, "revert", "--abort")
                return False
        return suite_green(wt)
    finally:
        _git(repo, "worktree", "remove", "--force", str(wt))
        _git(repo, "worktree", "prune")
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="check_task_commit.py")
    p.add_argument("task", nargs="?")
    p.add_argument("--green", action="store_true")
    p.add_argument("--revert-check", action="store_true")
    p.add_argument("--with-dependents", action="store_true")
    p.add_argument("--repo", default=".")
    p.add_argument("--self-test", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.self_test:
        return self_test()
    if not a.task or not re.fullmatch(r"T\d+", a.task):
        print("usage error: task id like T001 required", file=sys.stderr)
        return 2
    repo = Path(a.repo)
    if not has_task_commit(repo, a.task):
        print(f"no commit with subject '{a.task}:'", file=sys.stderr)
        return 1
    if a.green and not suite_green(repo):
        print("suite not green", file=sys.stderr)
        return 1
    if a.revert_check and not revert_check(repo, a.task, a.with_dependents):
        print("revert check failed", file=sys.stderr)
        return 1
    return 0


def _commit(repo, subject, files):
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A", check=True)
    _git(repo, "commit", "--allow-empty", "-m", subject, check=True)


def build_sample_repo(repo: Path):
    """T001, T002 (changes VALUE), T003 (red test), T004 (changes VALUE again)."""
    _git(repo, "init", "-q", check=True)
    _commit(repo, "T001: base", {
        "base.py": "VALUE = 1\n",
        "test_base.py": "import base\n\ndef test_v():\n    assert base.VALUE >= 1\n"})
    _commit(repo, "T002: bump", {"base.py": "VALUE = 2\n"})
    _commit(repo, "T003: red", {"test_red.py": "def test_red():\n    assert False\n"})
    _commit(repo, "T004: bump again", {"base.py": "VALUE = 3\n"})


def self_test() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ctc_self_"))
    try:
        build_sample_repo(tmp)
        r = str(tmp)
        cases = [
            (["T001", "--repo", r], 0),
            (["T999", "--repo", r], 1),
            (["T00", "--repo", r], 1),
            (["T001", "--green", "--repo", r], 1),         # HEAD red due to T003
            (["T003", "--revert-check", "--repo", r], 0),  # removing red test -> green
            (["T002", "--revert-check", "--repo", r], 1),  # conflict with T004
            (["T999", "--revert-check", "--repo", r], 1),
            (["bad", "--repo", r], 2),
            ([], 2),
        ]
        ok = True
        for argv, want in cases:
            got = main(argv)
            if got != want:
                print(f"self-test FAIL {argv}: want {want} got {got}", file=sys.stderr)
                ok = False
        (tmp / "test_red.py").unlink()
        _commit(tmp, "T005: fix", {})
        if main(["T001", "--green", "--repo", r]) != 0:
            print("self-test FAIL green case", file=sys.stderr)
            ok = False
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
