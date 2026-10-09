import re

import pytest

from ai_gougi.config import get_config, keep, marker_len
from ai_gougi.truncate import truncate_opinion, truncate_output, truncate_stderr

CFG = get_config()


@pytest.mark.at("AT-11")
def test_opinion_lengths():
    t, total, tr = truncate_opinion("a" * 2000)
    assert (t, total, tr) == ("a" * 2000, 2000, False)
    t, total, tr = truncate_opinion("a" * 2001)
    assert tr and "省略 21 文字" in t and len(t) == 1992
    t, _, _ = truncate_opinion("a" * 2500)
    assert "省略 520 文字" in t
    t, total, tr = truncate_opinion("a" * 20000)
    assert "省略 18020 文字" in t and len(t) == 1995 and total == 20000


@pytest.mark.at("AT-11")
def test_marker_boundary_table():
    rows = [(21, 1992), (99, 1992), (100, 1993), (999, 1993), (1000, 1994),
            (10000, 1995), (18020, 1995)]
    for k, total in rows:
        t, _, _ = truncate_opinion("a" * (keep() + k))
        assert len(t) == total
        assert len(t) <= CFG.OPINION_MAX_CHARS
        assert marker_len(k) <= CFG.MARKER_RESERVE


@pytest.mark.at("AT-11")
def test_roundtrip_keep_plus_k():
    for n in (2001, 2002, 2500, 3000, 5000, 12000, 20000, 100000):
        t, total, tr = truncate_opinion("b" * n)
        assert tr and total == n
        head = t[: keep()]
        assert head == "b" * keep()
        k = int(re.search(r"省略 (\d+) 文字", t).group(1))
        assert len(head) + k == n


@pytest.mark.at("AT-06")
def test_output_stderr_truncation():
    t, total, tr = truncate_output("x" * 20000)
    assert (len(t), total, tr) == (20000, 20000, False)
    s = "".join(chr(65 + i % 26) for i in range(20001))
    t, total, tr = truncate_output(s)
    assert t == s[:20000] and tr is True and total == 20001
    e = "".join(chr(97 + i % 26) for i in range(4001))
    t, total, tr = truncate_stderr(e)
    assert t == e[-4000:] and len(t) == 4000 and tr is True and total == 4001
    assert truncate_stderr("y" * 4000) == ("y" * 4000, 4000, False)


def test_marker_at_06_11():
    import sys
    mod = sys.modules[__name__]
    marks = {}
    for name in ("test_opinion_lengths", "test_marker_boundary_table",
                 "test_roundtrip_keep_plus_k", "test_output_stderr_truncation"):
        fn = getattr(mod, name)
        marks[name] = {m.args[0] for m in fn.pytestmark if m.name == "at"}
    assert "AT-11" in marks["test_opinion_lengths"]
    assert "AT-11" in marks["test_marker_boundary_table"]
    assert "AT-11" in marks["test_roundtrip_keep_plus_k"]
    assert "AT-06" in marks["test_output_stderr_truncation"]


def test_invalid_input_raises():
    for bad in (None, 123):
        with pytest.raises(TypeError):
            truncate_opinion(bad)
    assert truncate_opinion("")[0] == ""
    for f in (truncate_output, truncate_stderr):
        with pytest.raises(TypeError):
            f(None)
