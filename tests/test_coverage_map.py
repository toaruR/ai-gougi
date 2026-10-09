from tests.coverage_map import (
    NOT_GUARDED,
    ROOT,
    check,
    design_text,
    marked_tests,
    parse_at_rows,
    parse_f_rows,
)


def test_every_at_in_design_has_marked_test():
    at_rows = parse_at_rows(design_text())
    expected = [f"AT-{i:02d}" for i in range(1, 25)]
    assert sorted(at_rows) == expected
    marked = marked_tests()
    missing = [a for a in expected if not marked.get(a)]
    assert missing == []


def test_every_f_mapped_or_not_guarded():
    text = design_text()
    f_rows = parse_f_rows(text)
    assert sorted(f_rows, key=lambda s: int(s[1:])) == [f"F{i}" for i in range(1, 29)]
    at_rows = parse_at_rows(text)
    marked = marked_tests()
    empty = [
        f
        for f in f_rows
        if not any(f in fs and marked.get(at) for at, fs in at_rows.items()) and f not in NOT_GUARDED
    ]
    assert empty == []


def test_not_guarded_text_matches_design():
    f_rows = parse_f_rows(design_text())
    for f in NOT_GUARDED:
        assert "**not guarded**" in f_rows[f], f
    assert sorted(NOT_GUARDED, key=lambda s: int(s[1:])) == [f"F{i}" for i in range(21, 29)]
    for f in ("F24", "F25", "F26", "F28"):
        assert "試験対象外" in NOT_GUARDED[f]
    # 設計書側で not guarded な F は NOT_GUARDED と一致
    in_design = {f for f, row in f_rows.items() if "**not guarded**" in row}
    assert in_design == set(NOT_GUARDED)


def test_checker_detects_missing_at():
    assert check() == 0
    assert check(drop="AT-07") >= 1


def test_scope_out_artifacts_absent():
    assert not (ROOT / ".github").exists()
    assert not (ROOT / "setup.py").exists()
    assert not (ROOT / "pyproject.toml").exists()
