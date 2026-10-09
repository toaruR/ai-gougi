import pytest

from ai_gougi import logging_util as lu
from ai_gougi.config import get_config


def test_log_event_stderr_one_line(capsys):
    lu.log_event("startup_env", "a\nb")
    out, err = capsys.readouterr()
    assert out == ""
    assert err.endswith("\n") and err.count("\n") == 1


def test_startup_env_line(capsys, monkeypatch):
    monkeypatch.delenv("AI_GOUGI_CHILD_ENV_EXTRA", raising=False)
    lu.log_startup_env(get_config())
    out, err = capsys.readouterr()
    assert "PYTHONUTF8=1" in err and err.count("\n") == 1 and out == ""
    monkeypatch.setenv("AI_GOUGI_CHILD_ENV_EXTRA", "")
    lu.log_startup_env(get_config())
    assert "無効" in capsys.readouterr().err


def test_is_git_repo_and_nongit_log(tmp_path, capsys, monkeypatch):
    # 祖先に .git があると True になるため判定を tmp 配下に限定して検証
    real = lu.os.path.exists
    root = str(tmp_path)

    def fake(p):
        return real(p) if str(p).startswith(root) else False

    monkeypatch.setattr(lu.os.path, "exists", fake)
    d = tmp_path / "w"
    d.mkdir()
    assert lu.is_git_repo(str(d)) is False
    lu.log_nongit_workdir(str(d))
    assert capsys.readouterr().err.count("\n") == 1
    (d / ".git").mkdir()
    assert lu.is_git_repo(str(d)) is True


def test_decode_newline_logs(capsys):
    lu.log_decode_replaced("claude")
    assert capsys.readouterr().err.count("\n") == 1
    lu.log_newline_replaced("agy")
    out, err = capsys.readouterr()
    assert err.count("\n") == 1 and out == ""


def test_unknown_kind_raises(capsys):
    with pytest.raises(ValueError):
        lu.log_event("bogus", "x")
    assert capsys.readouterr().err == ""
