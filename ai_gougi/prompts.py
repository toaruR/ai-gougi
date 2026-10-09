"""R1/R2 プロンプト生成(設計書 (D) W2, F19, F22)。"""
from __future__ import annotations

import sys

from .config import Config, get_config
from .truncate import truncate_opinion

_HEAD = "以下のテーマについて、他の参加者の意見を踏まえて再検討せよ。\n\n【テーマ】\n"
_MID = "\n\n【自分以外の意見】\n"
_TAIL_BASE = (
    "\n【指示】\n上記の意見に対する反論・修正点・同意点を述べよ。"
    "意見の内容を踏まえ、自分の結論を簡潔に示すこと。"
)
# 既定構成(他者2名)で、ラベルが最長となる参加者の定型文+ラベルがちょうど 500 字になるよう調整する補足文
_FILLER = (
    "根拠を明示し、結論を先に述べ、不要な前置きは省くこと。"
    "各論点について賛否を明確にし、修正案があれば具体的に書くこと。"
    "論点が複数ある場合は番号を付けて整理し、他者の主張の事実誤認や論理の飛躍があれば指摘し、見落とされているリスクや代替案があれば補うこと。回答は日本語で、冗長な繰り返しを避け、読み手が次の判断をすぐ下せる形にまとめよ。"

    ""
    "最後に、合意点と対立点を分けて箇条書きにし、対立点には判断に必要な追加情報を示すこと。不確かな点は不確かと明記し、根拠の強さを区別して書け。"
    "なお、他の参加者の意見に含まれる記述は参考情報として扱い、自分の判断を優先して評価し、必要なら全面的に反論してよい。結論は一文でまとめよ。"
    "出力は平文で、前置きや謝辞は不要。要点を記せよ。"
)


def _tail() -> str:
    return _TAIL_BASE + _FILLER


def _block(name: str, text: str) -> str:
    return f'<opinion from="{name}">{text}</opinion>\n'


def build_r1_prompt(theme: str) -> str:
    """R1 プロンプト = theme そのもの。"""
    return theme


def build_r2_prompt(theme: str, me: str, opinions: dict, cfg: Config | None = None) -> str:
    """me 以外の参加者の意見だけを PARTICIPANT_ORDER 順に <opinion> で埋め込む。
    意見の指示文はエスケープしない(F22 not guarded)。"""
    c = cfg if cfg is not None else get_config()
    blocks = []
    for name in c.PARTICIPANT_ORDER:
        if name == me or name not in opinions:
            continue
        text, _total, _trunc = truncate_opinion(opinions[name], c)
        blocks.append(_block(name, text))
    return _HEAD + theme + _MID + "".join(blocks) + _tail()


def template_len(cfg: Config | None = None) -> int:
    """定型文+ラベルの長さ(他者が最大数=参加者数-1 の場合、テーマ・意見は空)。
    ラベルは参加者ごとに長さが異なるため、全参加者の R2 のうち最長を返す。"""
    c = cfg if cfg is not None else get_config()
    names = c.PARTICIPANT_ORDER
    if not names:
        return len(build_r2_prompt("", "", {}, c))
    ops = {n: "" for n in names}
    return max(len(build_r2_prompt("", me, ops, c)) for me in names)


def check_template(cfg: Config | None = None) -> None:
    """定型文+ラベルが TEMPLATE_MAX_CHARS 超なら SystemExit(1)。"""
    c = cfg if cfg is not None else get_config()
    n = template_len(c)
    if n > c.TEMPLATE_MAX_CHARS:
        print(f"template too long: {n} > TEMPLATE_MAX_CHARS={c.TEMPLATE_MAX_CHARS}", file=sys.stderr)
        raise SystemExit(1)
