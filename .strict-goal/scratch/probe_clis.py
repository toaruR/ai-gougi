"""Probe real CLIs (claude/codex/agy) and taskkill; emit probe_report.json + cli_probe.log."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ("claude", "codex", "agy")


def _version(path):
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True,
                           timeout=15, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


def probe_cli(name, force_missing):
    path = None if force_missing else shutil.which(name)
    if not path:
        return {"found": False, "path": None, "ext": None, "exe_len": None, "version": None}
    return {"found": True, "path": path, "ext": os.path.splitext(path)[1].lower(),
            "exe_len": len(path), "version": _version(path)}


def run_probe(out, log):
    force = os.environ.get("AI_GOUGI_PROBE_FORCE_MISSING") == "1"
    report = {
        "schema": 1,
        "platform": sys.platform,
        "taskkill_available": (not force) and shutil.which("taskkill") is not None,
        "clis": {n: probe_cli(n, force) for n in NAMES},
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(log, "a", encoding="utf-8") as f:
        for n in NAMES:
            c = report["clis"][n]
            f.write(f"{n}: found={c['found']} path={c['path']} ext={c['ext']} "
                    f"exe_len={c['exe_len']} version={c['version']}\n")
        f.write(f"taskkill_available={report['taskkill_available']} platform={report['platform']}\n")
    return 0


def validate(path):
    try:
        r = json.loads(Path(path).read_text(encoding="utf-8"))
        assert r["schema"] == 1
        assert isinstance(r["platform"], str)
        assert isinstance(r["taskkill_available"], bool)
        for n in NAMES:
            c = r["clis"][n]
            assert isinstance(c["found"], bool)
            for k in ("path", "ext", "exe_len", "version"):
                assert k in c
            if c["found"]:
                assert isinstance(c["path"], str) and c["path"]
                assert isinstance(c["ext"], str)
                assert isinstance(c["exe_len"], int)
            else:
                assert c["path"] is None and c["ext"] is None
        return 0
    except Exception as e:
        print(f"invalid report {path}: {e!r}", file=sys.stderr)
        return 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "probe_report.json"))
    ap.add_argument("--log", default=str(HERE / "cli_probe.log"))
    ap.add_argument("--validate", metavar="PATH")
    a = ap.parse_args(argv)
    if a.validate:
        return validate(a.validate)
    return run_probe(a.out, a.log)


if __name__ == "__main__":
    sys.exit(main())
