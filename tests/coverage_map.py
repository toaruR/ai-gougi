"""設計9節(AT表)と7節(F表)の網羅検査ヘルパ。"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "design-ai-gougi.md"
TESTS_DIR = Path(__file__).resolve().parent

NOT_GUARDED_MARK = "**not guarded**"

# F21〜F28 は設計書で not guarded。F24/F25/F26/F28 は試験対象外。
NOT_GUARDED = {
    "F21": "設計書 not guarded: % は正当な文字で汎用エスケープなし",
    "F22": "設計書 not guarded: <opinion> は区切りのみ",
    "F23": "設計書 not guarded: F15 は事後検知のみ",
    "F24": "試験対象外: クライアント側MCPタイムアウトはサーバー外の事象",
    "F25": "試験対象外: サーバー異常終了時の途中結果は永続化しない設計",
    "F26": "試験対象外: 巨大出力のメモリ内バッファは防御しない設計",
    "F27": "設計書 not guarded: NONZERO_EXIT で表面化",
    "F28": "試験対象外: 回収不能プロセスは timed_out=true で返し放置",
}


def design_text():
    return DESIGN.read_text(encoding="utf-8")


def parse_f_rows(text=None):
    """{'F1': 行全体, ...}"""
    text = design_text() if text is None else text
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*(F\d+)\s*\|", line)
        if m:
            rows[m.group(1)] = line
    return rows


def parse_at_rows(text=None):
    """{'AT-01': ['F9'], ...}"""
    text = design_text() if text is None else text
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*(AT-\d+)\s*\|\s*([^|]*)\|", line)
        if m:
            rows[m.group(1)] = re.findall(r"F\d+", m.group(2))
    return rows


def _is_at_mark(node):
    """pytest.mark.at("AT-nn") 呼び出しなら ID を返す。"""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "at"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def marked_tests(tests_dir=None):
    """{'AT-nn': {'file::test_name', ...}} を tests/*.py の AST から得る。"""
    tests_dir = Path(tests_dir) if tests_dir else TESTS_DIR
    result = {}
    for path in sorted(tests_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_ids = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
            ):
                vals = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
                module_ids += [i for i in map(_is_at_mark, vals) if i]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                ids = [i for i in map(_is_at_mark, node.decorator_list) if i] + module_ids
                for i in ids:
                    result.setdefault(i, set()).add(f"{path.name}::{node.name}")
    return result


def check(drop=None):
    """網羅の問題数を返す。drop='AT-07' でその AT の試験対応を無かった事にする。"""
    problems = 0
    text = design_text()
    at_rows = parse_at_rows(text)
    f_rows = parse_f_rows(text)
    marked = {k: v for k, v in marked_tests().items() if k != drop}
    # (1) AT -> 試験
    for at in at_rows:
        if not marked.get(at):
            problems += 1
    # (2) F -> AT経由の試験 or NOT_GUARDED
    for f in f_rows:
        via_at = any(f in fs and marked.get(at) for at, fs in at_rows.items())
        if not via_at and f not in NOT_GUARDED:
            problems += 1
    # (3) NOT_GUARDED の整合
    for f in NOT_GUARDED:
        if NOT_GUARDED_MARK not in f_rows.get(f, ""):
            problems += 1
    return problems
