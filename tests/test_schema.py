import json
import re
from pathlib import Path

import jsonschema
import pytest

from ai_gougi.schema import (
    DESIGN_SCHEMA,
    SCHEMA,
    is_valid,
    make_ask_result,
    make_prelaunch_error,
    validate,
)

DESIGN = (Path(__file__).resolve().parent.parent / "docs" / "design-ai-gougi.md").read_text(encoding="utf-8")
SEC = DESIGN.split("### 5.1 JSON Schema", 1)[1].split("### 5.2", 1)[0]
BLOCKS = re.findall(r"```json\n(.*?)\n```", SEC, re.S)


def test_schema_equals_design_block():
    block = json.loads(BLOCKS[0])
    assert block == DESIGN_SCHEMA
    assert SCHEMA["$ref"] == "#/$defs/AskResult"
    assert {k: v for k, v in SCHEMA.items() if k != "$ref"} == block


def test_design_examples_valid():
    ex = [json.loads(line) for line in BLOCKS[1].splitlines() if line.strip()]
    assert len(ex) == 3
    validate(ex[0], "AskResult")
    validate(ex[1], "DeliberateOutput")
    validate(ex[2], "DeliberateOutput")
    jsonschema.Draft202012Validator(SCHEMA)  # 構築可能
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def _ok():
    return make_ask_result("claude", ok=True, exit_code=0, stdout="hello")


def test_negative_invariants():
    base = _ok()
    validate(base)
    assert not is_valid({**base, "error_code": "NONZERO_EXIT", "error_message": "x"})
    assert not is_valid({**base, "ok": False, "error_code": None, "error_message": None})
    assert not is_valid({**base, "ok": False, "error_code": "NONZERO_EXIT", "error_message": None})
    assert not is_valid({**base, "error_message": "x"})
    with pytest.raises(jsonschema.ValidationError):
        validate({**base, "error_code": "NONZERO_EXIT"})


def test_prelaunch_error_fixed_values():
    r = make_prelaunch_error("claude", "BUSY", "msg")
    assert r["ok"] is False and r["exit_code"] is None and r["workdir_check"] == "skipped"
    assert r["stdout"] == r["stderr"] == ""
    assert r["stdout_total_chars"] == 0 and r["stderr_total_chars"] == 0
    assert r["timed_out"] is False and r["duration_ms"] == 0
    assert r["stdout_truncated"] is False and r["stderr_truncated"] is False
    assert r["error_code"] == "BUSY" and r["error_message"] == "msg"
    validate(r)


def test_unknown_participant_rejected():
    assert not is_valid({**_ok(), "participant": "gemini"})
    assert not is_valid(make_prelaunch_error("gemini", "BUSY", "m"))
    with pytest.raises(jsonschema.ValidationError):
        validate(make_prelaunch_error("gemini", "BUSY", "m"))
