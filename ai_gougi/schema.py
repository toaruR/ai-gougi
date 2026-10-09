"""設計書5.1の JSON Schema・TypedDict・結果ビルダー・検証関数。"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional, TypedDict

import jsonschema

_SCHEMA_JSON = r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$defs":{
 "AskInput":{"type":"object","properties":{"prompt":{"type":"string"}},"required":["prompt"],"additionalProperties":false},
 "DeliberateInput":{"type":"object","properties":{"theme":{"type":"string"},"rounds":{"type":"integer"}},"required":["theme"],"additionalProperties":false},
 "AskResult":{"type":"object","properties":{"participant":{"enum":["claude","codex","agy"]},"ok":{"type":"boolean"},"exit_code":{"type":["integer","null"]},"stdout":{"type":"string"},"stderr":{"type":"string"},"stdout_total_chars":{"type":"integer"},"stderr_total_chars":{"type":"integer"},"stdout_truncated":{"type":"boolean"},"stderr_truncated":{"type":"boolean"},"timed_out":{"type":"boolean"},"duration_ms":{"type":"integer"},"workdir_check":{"enum":["unchanged","changed","skipped"]},"error_code":{"enum":["INVALID_INPUT","PROMPT_TOO_LONG","CMDLINE_TOO_LONG","CLI_NOT_FOUND","SPAWN_FAILED","TIMEOUT","NONZERO_EXIT","EMPTY_OUTPUT","BUSY",null]},"error_message":{"type":["string","null"]}},"required":["participant","ok","exit_code","stdout","stderr","stdout_total_chars","stderr_total_chars","stdout_truncated","stderr_truncated","timed_out","duration_ms","workdir_check","error_code","error_message"],"additionalProperties":false,"allOf":[{"if":{"properties":{"ok":{"const":true}}},"then":{"properties":{"error_code":{"type":"null"}}},"else":{"properties":{"error_code":{"type":"string"}}}},{"if":{"properties":{"error_code":{"type":"null"}}},"then":{"properties":{"error_message":{"type":"null"}}},"else":{"properties":{"error_message":{"type":"string"}}}}]},
 "AskResultClaude":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"claude"}}},
 "AskResultCodex":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"codex"}}},
 "AskResultAgy":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"agy"}}},
 "DeliberateOutput":{"type":"object","properties":{"status":{"enum":["ok","partial","failed"]},"error_code":{"enum":["INVALID_INPUT","THEME_TOO_LONG","BUSY","ALL_FAILED",null]},"error_message":{"type":["string","null"]},"rounds_requested":{"type":"integer"},"rounds_executed":{"type":"integer"},"skipped_reason":{"enum":["S1_BELOW_MIN",null]},"elapsed_ms":{"type":"integer"},"rounds":{"type":"array","items":{"type":"object","properties":{"round":{"type":"integer","minimum":1},"results":{"type":"array","items":{"$ref":"#/$defs/AskResult"}}},"required":["round","results"],"additionalProperties":false}}},"required":["status","error_code","error_message","rounds_requested","rounds_executed","skipped_reason","elapsed_ms","rounds"],"additionalProperties":false}
}}'''

DESIGN_SCHEMA: dict = json.loads(_SCHEMA_JSON)  # 設計書5.1のブロックそのもの

# 主結果型 AskResult を最上位 $ref に据える(Draft202012Validator(SCHEMA) 単体で AskResult 検証になる)
SCHEMA: dict = {**DESIGN_SCHEMA, "$ref": "#/$defs/AskResult"}

Participant = Literal["claude", "codex", "agy"]


class AskResult(TypedDict):
    participant: str
    ok: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    stdout_total_chars: int
    stderr_total_chars: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    duration_ms: int
    workdir_check: Literal["unchanged", "changed", "skipped"]
    error_code: Optional[str]
    error_message: Optional[str]


class AskResultClaude(AskResult):
    participant: Literal["claude"]  # type: ignore[misc]


class AskResultCodex(AskResult):
    participant: Literal["codex"]  # type: ignore[misc]


class AskResultAgy(AskResult):
    participant: Literal["agy"]  # type: ignore[misc]


class RoundResult(TypedDict):
    round: int
    results: list[AskResult]


class DeliberateOutput(TypedDict):
    status: Literal["ok", "partial", "failed"]
    error_code: Optional[str]
    error_message: Optional[str]
    rounds_requested: int
    rounds_executed: int
    skipped_reason: Optional[str]
    elapsed_ms: int
    rounds: list[RoundResult]


def _validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{name}"}
    )


def validate(instance: Any, name: str = "AskResult") -> None:
    """$defs[name] で検証。違反時は jsonschema.ValidationError。"""
    _validator(name).validate(instance)


def is_valid(instance: Any, name: str = "AskResult") -> bool:
    return _validator(name).is_valid(instance)


def validate_ask_result(instance: Any) -> None:
    validate(instance, "AskResult")


def validate_deliberate_output(instance: Any) -> None:
    validate(instance, "DeliberateOutput")


def make_ask_result(
    participant: str,
    *,
    ok: bool,
    exit_code: Optional[int],
    stdout: str = "",
    stderr: str = "",
    stdout_total_chars: Optional[int] = None,
    stderr_total_chars: Optional[int] = None,
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
    timed_out: bool = False,
    duration_ms: int = 0,
    workdir_check: str = "unchanged",
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> AskResult:
    return {
        "participant": participant,
        "ok": ok,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_total_chars": len(stdout) if stdout_total_chars is None else stdout_total_chars,
        "stderr_total_chars": len(stderr) if stderr_total_chars is None else stderr_total_chars,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "workdir_check": workdir_check,
        "error_code": error_code,
        "error_message": error_message,
    }  # type: ignore[return-value]


def make_prelaunch_error(participant: str, error_code: str, error_message: str) -> AskResult:
    """起動前エラー: ok=false, exit_code=null, workdir_check=skipped, 文字列空, 数値0, 真偽false。"""
    return make_ask_result(
        participant,
        ok=False,
        exit_code=None,
        workdir_check="skipped",
        error_code=error_code,
        error_message=error_message,
    )
