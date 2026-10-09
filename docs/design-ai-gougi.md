# AI-Gougi 設計書

## 1. 背景と目的
Claude Code / Codex CLI / Antigravity CLI(agy) の全参加者に同一テーマを諮り合議したい。各CLIは単体のヘッドレス実行しか持たないため、Python + FastMCP のサーバー「AI-Gougi」が各CLIを subprocess でラップしてツール公開する。司会は呼び出し側の Claude Code（サーバーは司会をしない）。Windows ネイティブ、3者とも読み取り専用、応答が数分かかるため長いタイムアウトを取り、一部が失敗しても続行する。

## 2. アーキテクチャ
```
Claude Code(司会/ラウンド3) --MCP stdio--> AI-Gougi (FastMCP, asyncio)
   ask_claude / ask_codex / ask_agy / deliberate
        |  run_cli(participant, prompt)  -- 唯一のsubprocess入口
        +--> claude.exe/cmd | codex.cmd | agy.cmd/exe   (cwd=WORKDIR, shell=False)
```
`run_cli`: 検証→枠予約→snapshot→起動→待機/kill→切り詰め→結果生成。`ask_*` は `run_cli` 1回、`deliberate` は並列 `run_cli` を最大 MAX_ROUNDS ラウンド（R1=独立意見、R2=反論、R3=司会が整理）。

## 3. 既定値表（全閾値・設定値・書式リテラルの唯一の定義箇所）
他節は名前のみで参照し、数値の代入は 4.1 の1回だけ。全行は環境変数 `AI_GOUGI_<名前>` で上書き可。この表にない設定は存在しない（本文の名前は script で一致検査済み）。
| 名前 | 既定値 | 理由 |
|---|---|---|
| WORKDIR | サーバー起動時cwdの絶対パス | agy は --cwd 無効、cwd 引数で固定 |
| BIN_claude / BIN_codex / BIN_agy | `claude` / `codex` / `agy` | 各CLIの導入コマンド名。固定パスは導入先差で壊れるため `shutil.which` で解決（.cmd shim 対応）、PATH 外は絶対パスで上書き。agy は .cmd/.exe 両方で導入されるため拡張子で改行規則を切替える |
| TIMEOUT_SEC | 600 | 要件の10分 |
| KILL_WAIT_SEC | 5 | taskkill 後の回収待ち。T_max に含める |
| TASKKILL_FLAGS | `/T /F` | /T で孫まで kill、/F で終了要求の無視に対処 |
| CHILD_ENV_EXTRA | `PYTHONUTF8=1` | Python 製 CLI の出力を ENCODING と一致させる（F13） |
| ENCODING | utf-8 (decode errors=replace) | 不正バイトは U+FFFD、例外にしない |
| PROMPT_MAX_CHARS | 7000 | 全CLI共通。R2(4.1 D)が収まる値。agy は 4.1 B で別途判定 |
| CMDLINE_MAX_CHARS | 8000 | cmd.exe 上限 8191 に 191 字の余白 |
| AGY_EXE_LEN_REF | 38 | 検算・テスト用の基準 exe 長（`C:\Users\u\AppData\Roaming\npm\agy.cmd`）。実行時は実測 E を使う |
| CMDLINE_FIXED_CHARS | 6 | `exe -p "…"` の固定部＝空白1+`-p`2+空白1+囲み引用符2 |
| THEME_MAX_CHARS | 1500 | ラウンド2の配分（4.1 D） |
| OPINION_MAX_CHARS | 2000 | 1意見の上限（マーカー込み） |
| MARKER_FORMAT | `"\n…[省略 {k} 文字]"` | 切り詰め量 k を明示する。長さ m(k)=10+桁数: 2桁12 / 3桁13 / 4桁14 / 5桁15 字 |
| MARKER_RESERVE | 20 | 最大マーカー長15字(5桁)に5字の余裕 |
| TEMPLATE_MAX_CHARS | 500 | R2定型文+ラベルの上限。超過なら起動時にエラー終了 |
| OUTPUT_MAX_CHARS | 20000 | stdout は先頭を残す。最悪返却量は 4.1 H |
| STDERR_MAX_CHARS | 4000 | stderr は末尾を残す（エラーは末尾に出る） |
| MIN_SUCCESS_R2 | 2 | 1人では反論相手がいない |
| DEFAULT_ROUNDS | 2 | サーバー担当は R1・R2 |
| MAX_ROUNDS | 2 | R3 は司会の担当 |
| MAX_CONCURRENT_PROCS | 3 | 参加者数（deliberate 1回の同時数） |
| SNAPSHOT_MAX_FILES | 5000 | 走査コスト上限 |
| SNAPSHOT_EXCLUDE | `.git`,`node_modules` | 巨大/無関係 |
| PARTICIPANT_ORDER | claude, codex, agy | 並列の完了順は非決定的なので固定し添字比較を可能にする。agy は argv 経路で最も脱落しやすい（F5）ため末尾に置き、脱落しても他の添字が動かない |

導出記号（定義のみ）:
| 記号 | 定義 |
|---|---|
| P / T_max(r) | TIMEOUT_SEC+KILL_WAIT_SEC / r×P |
| E | `len(list2cmdline([exe]))` 実測 |
| B | E + CMDLINE_FIXED_CHARS |
| n0 / n / x | 元長 / 置換後長 / list2cmdline の増加字数。L=B+n+x |
| N_safe | floor((CMDLINE_MAX_CHARS−B)/2) |
| x_lim(n0) | CMDLINE_MAX_CHARS−B−n0 |
| keep | OPINION_MAX_CHARS−MARKER_RESERVE |
| k / m(k) | len − keep / マーカー長 |
| W2 | TEMPLATE_MAX_CHARS + THEME_MAX_CHARS + 2×OPINION_MAX_CHARS |
| S1 | ラウンド1で ok だった参加者数 |

## 4. CLI起動仕様（Windows）
| 参加者 | argv（BIN_*は which で絶対パス化） | プロンプト経路 |
|---|---|---|
| claude | `[BIN_claude, "-p", "--permission-mode", "plan"]` | stdin(UTF-8) |
| codex | `[BIN_codex, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"]` | stdin(UTF-8) |
| agy | `[BIN_agy, "-p", <prompt>]` | argv（stdinは `DEVNULL`） |

共通規約:
1. `asyncio.create_subprocess_exec`（`shell=False`）、`cwd=WORKDIR`、stdout/stderr=PIPE、環境は継承+CHILD_ENV_EXTRA。stdin 経路のCLIは書込後に close(EOF)。
2. `.cmd` shim は cmd.exe 経由で起動するため cmd.exe 上限が agy の argv に効く（stdin 経路の claude, codex は無関係）。
3. agy は `list2cmdline(argv)` の実長 L が CMDLINE_MAX_CHARS を超えたら起動せず CMDLINE_TOO_LONG。`.cmd` のみ、改行(1字)をリテラル `\n`(2字)に置換して渡す（cmd.exe は改行で行切断する）。`.exe` は置換せず改行を保持する。
4. 読み取り専用は `--sandbox read-only` と claude の `--permission-mode plan` が担う。`--skip-git-repo-check` は git 管理外 WORKDIR で codex を動かすため。
5. 待機は `wait_for(communicate(), TIMEOUT_SEC)`。超過時は `taskkill /PID <pid> TASKKILL_FLAGS` でツリーを kill し、`KILL_WAIT_SEC` 以内に回収、`timed_out=true`。
6. 成功判定 `ok` = (exit_code==0) かつ (stdout.strip() が非空) かつ not timed_out。

### 4.1 数式と検証（python で検算済み）
| 式 | 入力 | 結果 | 境界・往復検査 |
|---|---|---|---|
| (A) T_max(r) | r=1, 2 | 605, 1210 秒 | r ≤ MAX_ROUNDS。r=3（1815）は MAX_ROUNDS=3 上書き時のみ、既定では INVALID_INPUT で到達不能。T_t=3, K_t=2 で 5, 10。`elapsed_ms` ≤ 1000×T_max（AT-03, 17） |
| (B1) N_safe | E=AGY_EXE_LEN_REF | B=44, N_safe=3978 | 最悪形（空白1+引用符 n0−1）: 3978 → L=7999 通す、3979 → L=8001 拒否（AT-05） |
| (B2) x_lim | n0=PROMPT_MAX_CHARS | x_lim=956 | x=0 → L=7044、956 → L=8000 通す、957 → L=8001 拒否（AT-05） |
| (C) 切り詰め | len=2000/2001/2500/20000 | keep=1980、原文 / k=21 / k=520 / k=18020 | 往復 keep+k=len。全体 ≤ OPINION_MAX_CHARS（AT-11） |
| (D) W2 | 既定値 | 6000 ≤ PROMPT_MAX_CHARS | agy の x_lim=1956 超で CMDLINE_TOO_LONG（AT-16） |
| (E) 出力 | stdout 20000/20001、stderr 4001 字 | そのまま / 先頭20000+truncated, total=20001 / 末尾4000 | AT-06 |
| (F) 続行 | S1=0,1,2,3 | ALL_FAILED / R2省略(S1_BELOW_MIN) / 各1意見 / 各2意見 | 意見数=S1−1。S1−1 ≥ 1 ⇔ S1 ≥ MIN_SUCCESS_R2 |
| (G) 枠 | (running,need)=(0,3),(1,3),(2,1),(3,1) | 受理, BUSY, 受理, BUSY | 受理 ⇔ running+need ≤ MAX_CONCURRENT_PROCS（AT-09） |
| (H) 返却量 | 3者×2ラウンド×24000 | 144000 字 | 参加者×MAX_ROUNDS×(OUTPUT+STDERR 上限) |

式の定義:
- (B) x の内訳（各+1）: ①`"` は `\"` で+1、②`"` 直前および末尾の連続 `\` は倍化で各+1、③`.cmd` の改行→`\n` で+1。囲み引用符は CMDLINE_FIXED_CHARS に含む。各文字は高々2字なので L ≤ B + 2×n0、n0 ≤ N_safe なら中身に関わらず通る。超える場合は実測 L で判定する。

マーカー長の境界（len = keep + k、合計 = keep + m(k)）:
| k | m(k) | len | 合計 |
|---|---|---|---|
| 21（最小） | 12 | 2001 | 1992 |
| 99 | 12 | 2079 | 1992 |
| 100 | 13 | 2080 | 1993 |
| 999 | 13 | 2979 | 1993 |
| 1000 | 14 | 2980 | 1994 |
| 10000 | 15 | 11980 | 1995 |
| 18020（最大） | 15 | 20000 | 1995 |

全行で 合計 ≤ OPINION_MAX_CHARS、m(k) ≤ MARKER_RESERVE。

## 5. ツール仕様
### 5.1 JSON Schema
`rounds` の範囲・空白のみ・長さ上限は、サーバーが構造化エラー(error_code)で返すためスキーマには型のみを置く（スキーマ違反は MCP層エラーになる）。
```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","$defs":{
 "AskInput":{"type":"object","properties":{"prompt":{"type":"string"}},"required":["prompt"],"additionalProperties":false},
 "DeliberateInput":{"type":"object","properties":{"theme":{"type":"string"},"rounds":{"type":"integer"}},"required":["theme"],"additionalProperties":false},
 "AskResult":{"type":"object","properties":{"participant":{"enum":["claude","codex","agy"]},"ok":{"type":"boolean"},"exit_code":{"type":["integer","null"]},"stdout":{"type":"string"},"stderr":{"type":"string"},"stdout_total_chars":{"type":"integer"},"stderr_total_chars":{"type":"integer"},"stdout_truncated":{"type":"boolean"},"stderr_truncated":{"type":"boolean"},"timed_out":{"type":"boolean"},"duration_ms":{"type":"integer"},"workdir_check":{"enum":["unchanged","changed","skipped"]},"error_code":{"enum":["INVALID_INPUT","PROMPT_TOO_LONG","CMDLINE_TOO_LONG","CLI_NOT_FOUND","SPAWN_FAILED","TIMEOUT","NONZERO_EXIT","EMPTY_OUTPUT","BUSY",null]},"error_message":{"type":["string","null"]}},"required":["participant","ok","exit_code","stdout","stderr","stdout_total_chars","stderr_total_chars","stdout_truncated","stderr_truncated","timed_out","duration_ms","workdir_check","error_code","error_message"],"additionalProperties":false,"allOf":[{"if":{"properties":{"ok":{"const":true}}},"then":{"properties":{"error_code":{"type":"null"}}},"else":{"properties":{"error_code":{"type":"string"}}}},{"if":{"properties":{"error_code":{"type":"null"}}},"then":{"properties":{"error_message":{"type":"null"}}},"else":{"properties":{"error_message":{"type":"string"}}}}]},
 "AskResultClaude":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"claude"}}},
 "AskResultCodex":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"codex"}}},
 "AskResultAgy":{"$ref":"#/$defs/AskResult","properties":{"participant":{"const":"agy"}}},
 "DeliberateOutput":{"type":"object","properties":{"status":{"enum":["ok","partial","failed"]},"error_code":{"enum":["INVALID_INPUT","THEME_TOO_LONG","BUSY","ALL_FAILED",null]},"error_message":{"type":["string","null"]},"rounds_requested":{"type":"integer"},"rounds_executed":{"type":"integer"},"skipped_reason":{"enum":["S1_BELOW_MIN",null]},"elapsed_ms":{"type":"integer"},"rounds":{"type":"array","items":{"type":"object","properties":{"round":{"type":"integer","minimum":1},"results":{"type":"array","items":{"$ref":"#/$defs/AskResult"}}},"required":["round","results"],"additionalProperties":false}}},"required":["status","error_code","error_message","rounds_requested","rounds_executed","skipped_reason","elapsed_ms","rounds"],"additionalProperties":false}
}}
```
例（`jsonschema` 4.23.0 / Draft 2020-12 で検証済み、負例は拒否）。順に ok=true の AskResult、ok / partial の DeliberateOutput。紙面では results を1件に縮約（実機の R1 は3件）:
```json
{"participant":"claude","ok":true,"exit_code":0,"stdout":"hello","stderr":"","stdout_total_chars":5,"stderr_total_chars":0,"stdout_truncated":false,"stderr_truncated":false,"timed_out":false,"duration_ms":1200,"workdir_check":"unchanged","error_code":null,"error_message":null}
{"status":"ok","error_code":null,"error_message":null,"rounds_requested":1,"rounds_executed":1,"skipped_reason":null,"elapsed_ms":1300,"rounds":[{"round":1,"results":[{"participant":"claude","ok":true,"exit_code":0,"stdout":"hello","stderr":"","stdout_total_chars":5,"stderr_total_chars":0,"stdout_truncated":false,"stderr_truncated":false,"timed_out":false,"duration_ms":1200,"workdir_check":"unchanged","error_code":null,"error_message":null}]}]}
{"status":"partial","error_code":null,"error_message":null,"rounds_requested":2,"rounds_executed":1,"skipped_reason":"S1_BELOW_MIN","elapsed_ms":1300,"rounds":[{"round":1,"results":[{"participant":"claude","ok":true,"exit_code":0,"stdout":"hello","stderr":"","stdout_total_chars":5,"stderr_total_chars":0,"stdout_truncated":false,"stderr_truncated":false,"timed_out":false,"duration_ms":1200,"workdir_check":"unchanged","error_code":null,"error_message":null}]}]}
```
- `ask_*`: inputSchema=`AskInput`、outputSchema=`AskResultClaude` / `AskResultCodex` / `AskResultAgy`（participant を固定）。`ok=false` で `isError=true`（内容は同じ構造化結果）。
- `deliberate`: inputSchema=`DeliberateInput`（rounds省略時 DEFAULT_ROUNDS、範囲 1..MAX_ROUNDS はサーバーが検査）、outputSchema=`DeliberateOutput`。`status=failed` のみ `isError=true`。
- 不変条件（スキーマで強制）: `ok=true` ⇔ `error_code=null` ⇔ `error_message=null`。
- 起動前エラー（INVALID_INPUT / PROMPT_TOO_LONG / CMDLINE_TOO_LONG / CLI_NOT_FOUND / BUSY）の ask_*: `ok=false, exit_code=null, workdir_check="skipped"`、文字列は空、数値は 0、真偽は false、原因は `error_message`。

### 5.2 deliberate の status 判定
`ok` = 要求ラウンドを全て実施し、実施した全ラウンドで全参加者が `ok`。`failed` = S1=0 または入力エラー。それ以外は `partial`。

### 5.3 エラー条件表（上から最初に当たる行を採用）
| 対象 | error_code | 条件 | 動作 |
|---|---|---|---|
| ask_* | INVALID_INPUT | prompt が空白のみ | 起動せず |
| ask_* | PROMPT_TOO_LONG | len(prompt) > PROMPT_MAX_CHARS | 起動せず |
| 全 | BUSY | 条件(G)を満たさない | 起動せず |
| 全 | CLI_NOT_FOUND | `shutil.which(BIN_*)` が None | 起動せず |
| ask_agy | CMDLINE_TOO_LONG | 実測L > CMDLINE_MAX_CHARS（E は which 結果で確定） | 起動せず |
| 全 | SPAWN_FAILED | OSError で起動不可 | 例外文を error_message に |
| 全 | TIMEOUT | TIMEOUT_SEC 超過（kill後） | timed_out=true, 部分出力保持 |
| 全 | NONZERO_EXIT | exit_code≠0 | stdout/stderr 返却 |
| 全 | EMPTY_OUTPUT | exit_code==0 で stdout が空白のみ | ok=false |
| deliberate | INVALID_INPUT | theme が空白のみ、または rounds が 1..MAX_ROUNDS 外 | rounds=[] |
| deliberate | THEME_TOO_LONG | len(theme) > THEME_MAX_CHARS | rounds=[] |
| deliberate | BUSY | 条件(G) need=参加者数 を満たさない | rounds=[] |
| deliberate | ALL_FAILED | S1=0 | rounds にR1結果を残す |

### 5.4 FastMCP ツール定義
```python
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

mcp = FastMCP("ai-gougi")   # AskResultClaude 等は 5.1 の TypedDict

def _wrap(r: dict) -> CallToolResult:
    failed = (r["status"] == "failed") if "status" in r else (not r["ok"])
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(r, ensure_ascii=False))],
                          structuredContent=r, isError=failed)

@mcp.tool(description="Claude Code(plan mode)に質問する。")
async def ask_claude(prompt: str) -> Annotated[CallToolResult, AskResultClaude]:
    return _wrap(await run_cli("claude", prompt))

@mcp.tool(description="Codex CLI(read-only)に質問する。")
async def ask_codex(prompt: str) -> Annotated[CallToolResult, AskResultCodex]:
    return _wrap(await run_cli("codex", prompt))

@mcp.tool(description="Antigravity CLI(agy)に質問する。")
async def ask_agy(prompt: str) -> Annotated[CallToolResult, AskResultAgy]:
    return _wrap(await run_cli("agy", prompt))

@mcp.tool(description="全参加者に同一テーマを諮り、独立意見→反論の全結果を返す。整理は呼び出し側。")
async def deliberate(theme: str, rounds: int | None = None) -> Annotated[CallToolResult, DeliberateOutput]:
    return _wrap(await run_deliberate(theme, rounds))   # rounds=None は DEFAULT_ROUNDS
```
`run_deliberate` は 6 節の実装。
`mcp` 1.26.0 で outputSchema・`structuredContent`・`isError=true` を確認済み。

## 6. 合議ステートマシン
```
IDLE --入力検証NG--> FAILED(INVALID_INPUT|THEME_TOO_LONG)
IDLE --枠不足(G)--> FAILED(BUSY)
IDLE --受理, need=参加者数を予約--> R1_RUN   (並列, 各 TIMEOUT_SEC)
R1_RUN --全員終了--> R1_EVAL         (S1を算出)
R1_EVAL --S1=0--> FAILED(ALL_FAILED)
R1_EVAL --rounds=1--> DONE
R1_EVAL --S1=1--> DONE(skipped_reason=S1_BELOW_MIN)
R1_EVAL --S1>=MIN_SUCCESS_R2 かつ rounds>=2--> R2_RUN  (R1成功者のみ)
R2_RUN --全員終了--> DONE            (R2の失敗はR1意見を残し続行)
DONE/FAILED: 予約解放, status を5.2で決定
```
R1 プロンプト = theme。R2 プロンプト（定型文は TEMPLATE_MAX_CHARS 以内）: 「テーマ」「自分以外の意見(`<opinion from="codex">…</opinion>`、切り詰めは(C))」「反論・修正点・同意点を述べよ」。R1 で ok=false の参加者は R2 に不参加。R2 の失敗は `ok=false` で `rounds[1].results` に載る。結果は PARTICIPANT_ORDER 順。

## 7. 失敗モードと対策の対応表（1モード＝主機構1つ）
| ID | 失敗モード | 主機構 |
|---|---|---|
| F1 | CLI未インストール/PATH不備 | which解決 → CLI_NOT_FOUND |
| F2 | CLIのハング | TIMEOUT_SEC の `wait_for` |
| F3 | kill後に子孫プロセスが残る | TASKKILL_FLAGS の `/T` |
| F4 | 長すぎるプロンプト | PROMPT_MAX_CHARS 超で PROMPT_TOO_LONG |
| F5 | agy の argv が cmd.exe 上限超過 | 実測L > CMDLINE_MAX_CHARS で CMDLINE_TOO_LONG |
| F6 | agy `.cmd` で改行によりプロンプトが行切断 | 改行→リテラル `\n` 置換（4 規約3） |
| F7 | 巨大出力で呼び出し側が溢れる | OUTPUT_MAX_CHARS / STDERR_MAX_CHARS 切り詰め |
| F8 | 一部参加者の失敗で合議が止まる | 続行規則(F) |
| F9 | 部分失敗を ok と報告する | status 判定(5.2) |
| F10 | claude/codex が stdin 待ちで停止 | 書込後の close(EOF) |
| F11 | agy が stdin 待ちで停止 | stdin=`DEVNULL` |
| F12 | 文字化け・不正バイト | ENCODING の decode errors=replace |
| F13 | 子CLI(Python製)の出力が cp932 になる | CHILD_ENV_EXTRA |
| F14 | 同時起動の過多 | 予約制(G) → BUSY |
| F15 | agy が WORKDIR 内を書換（読取専用フラグなし） | snapshot 比較で `workdir_check=changed`（検知のみ） |
| F16 | claude が WORKDIR に書込 | `--permission-mode plan` |
| F17 | codex が WORKDIR に書込 | `--sandbox read-only` |
| F18 | git 管理外 WORKDIR で codex が起動拒否 | `--skip-git-repo-check` |
| F19 | R2埋め込み意見でプロンプト長超過 | OPINION_MAX_CHARS 切り詰め(C) |
| F20 | 空応答を成功扱い | EMPTY_OUTPUT判定(ok規則) |
| F21 | agy `.cmd` で `%VAR%` が cmd.exe に展開される | **not guarded**（`%` は正当な文字で安価な汎用エスケープがない） |
| F22 | 他者意見内の指示文によるインジェクション | **not guarded**（`<opinion>` は区切りのみ） |
| F23 | agy 書込の予防／plan mode の抜け穴 | **not guarded**（F15は事後検知のみ） |
| F24 | クライアントのMCPタイムアウトが T_max(2) より短い | **not guarded** |
| F25 | サーバー異常終了での途中結果消失 | **not guarded** |
| F26 | 巨大出力のメモリ内バッファ | **not guarded** |
| F27 | CLIの認証切れ | **not guarded**（NONZERO_EXIT で表面化） |
| F28 | kill後も回収できないプロセス | **not guarded**（`timed_out=true` で返し放置） |

## 8. 防御機構のトレードオフ
reject=エラー返却、warn=結果のフィールドで通知して続行、log=サーバー stderr に1行記録して続行。
| 機構 | 壊れる正当ケース・代替案・決定理由 | 決定 |
|---|---|---|
| PROMPT_MAX_CHARS / THEME_MAX_CHARS | 設計書全文や長大テーマを諮れない。要約は意図を壊し得るため拒否する。 | reject |
| CMDLINE 検査 | 引用符の多いコード片を agy に渡せない。一時ファイルは起動仕様を増やすため採らない。 | reject |
| TIMEOUT kill | 上限超の長考が切られる。呼び出し毎の延長は上限を無意味にするため採らず、部分出力を保持する。 | reject |
| OUTPUT 切り詰め | 超過した回答末尾が失われる。ファイル保存は永続化がスコープ外のため採らない。 | warn |
| OPINION 切り詰め | 長い意見の後半が R2 に届かない。要約は追加呼び出しを要するため採らず、通知する。 | warn |
| MIN_SUCCESS_R2 | 1者の自己批判をさせたい場合 R2 が省略される。自己レビューは合議でない。 | reject |
| EMPTY_OUTPUT | 空出力で正常終了する CLI が失敗扱いになる。成功扱いは空の意見を R2 に渡すため採らない。 | reject |
| BUSY | 並列呼び出しが失敗する。キュー待ちは TIMEOUT_SEC を超え得るため採らない。 | reject |
| 書込 snapshot | 並行編集や CLI のキャッシュ書込が誤検知になる。ACL 禁止は環境設定を要するため採らない。 | warn |
| stdin EOF / DEVNULL | 確認入力を求める CLI が失敗する。対話中継はヘッドレス前提に反するため採らない。 | reject |
| decode errors=replace | 非 UTF-8 の正当な出力が戻せない。生バイトは JSON にできないため採らない。 | log |
| which 解決 | PATH 外の導入済み CLI が CLI_NOT_FOUND になる。PATH 外探索は誤起動し得るため採らず、BIN_* を求める。 | reject |
| 改行置換(.cmd) | 複数行のコードブロックが agy `.cmd` にリテラル `\n` で届き整形が崩れる。複数行の拒否は用途を狭め、一時ファイルは起動仕様を増やすため採らず、cmd.exe の行切断で後続行が消える F6 を避けるため置換し、発生を記録する。 | log |
| --skip-git-repo-check | 指定ミスの git 管理外 WORKDIR でも codex が起動し、確認が働かない。管理外の拒否は任意ディレクトリでの合議を狭めるため採らず、読み取り専用は `--sandbox` が担保するので、管理外である旨を起動時に記録する。 | log |
| taskkill /T /F | /T は意図的に残された常駐の子まで殺し、/F は出力のフラッシュを許さず部分出力が欠ける。/T 無しは孫が残り（F3）、猶予付き終了は KILL_WAIT_SEC を超え得るため採らない。 | reject |
| CHILD_ENV_EXTRA | PYTHONUTF8=1 は子が呼ぶ別 Python ツールの挙動も変える。cp932 でのデコードは混在を判別できないため採らず、空文字で無効化でき、有効値を起動時に記録する。 | log |
| plan mode 系フラグ | 編集や実行が要る依頼が拒否される。`acceptEdits` は書込を許すため採らない。 | reject |

## 9. 受入テスト
stub を BIN_* で差し替える。値は 4.1 のもの。F 列は 7 節の失敗モード。
| ID | F | 入力/条件 | 期待出力 | 合否基準 |
|---|---|---|---|---|
| AT-01 | F9 | 全stub成功 | status=ok, rounds_executed=2, 各3件 | 全一致 |
| AT-02 | F9,F20 | ask_claude の stub が (a)exit0 で "hello" (b)exit0 で空白のみ | (a) ok=true, stdout="hello", error_code=null, isError=false (b) ok=false, EMPTY_OUTPUT, isError=true | 全一致 |
| AT-03 | F2 | TIMEOUT_SEC=T_t, KILL_WAIT_SEC=K_t, stub が長時間sleep | TIMEOUT, timed_out=true | 1000×T_t ≤ elapsed_ms ≤ 1000×T_max(1) |
| AT-04 | F4 | prompt長 PROMPT_MAX_CHARS / +1 | 受理 / PROMPT_TOO_LONG | 後者で起動0回 |
| AT-05 | F5 | agy `.cmd` stub: (a)n0=PROMPT_MAX_CHARS、引用符 または 改行 を x_lim / +1 個 (b)空白1+引用符(n0−1)で n0=N_safe / +1 | 実行 / CMDLINE_TOO_LONG | 実測 L (a)CMDLINE_MAX_CHARS / +1 (b)−1 / +1 |
| AT-06 | F7 | stdout OUTPUT_MAX_CHARS / +1 字、stderr STDERR_MAX_CHARS / +1 字 | +1 側のみ切り詰め(stdout先頭/stderr末尾)+total+truncated | 長さ・フラグ一致 |
| AT-07 | F8,F9 | codex が exit1 | codex=NONZERO_EXIT、R2は2者・各1意見、partial | 各自に他1者の意見のみ |
| AT-08 | F8,F9 | (a)claudeのみ成功 (b)3者失敗 | (a) rounds_executed=1, S1_BELOW_MIN, partial（R2 stub 呼び出し0回） (b) failed, ALL_FAILED, isError=true | 全一致 |
| AT-09 | F14 | (running,need)=(2,1)/(3,1)/(0,3)/(1,3)、deliberate のラウンド間の ask_claude | (2,1),(0,3)受理、他は BUSY | 同時数 ≤ MAX_CONCURRENT_PROCS |
| AT-10 | F4 | theme THEME_MAX_CHARS / +1 字、rounds=0,1..MAX_ROUNDS,MAX_ROUNDS+1、省略 | THEME_TOO_LONG / 範囲外は INVALID_INPUT / 省略は DEFAULT_ROUNDS | 全一致 |
| AT-11 | F19 | R1意見 OPINION_MAX_CHARS 字 / 4.1(C) の 2500 字 | 原文 / 先頭 keep 字+MARKER_FORMAT | keep+k=2500、全体 ≤ OPINION_MAX_CHARS |
| AT-12 | F15 | agy stub が (a)ファイル作成 (b)変更なし (c)SNAPSHOT_MAX_FILES+1 個 のファイル、(d)cwd を出力 | changed / unchanged / skipped、(d) stdout == WORKDIR | 4ケース一致 |
| AT-13 | F1,F8 | BIN_codex を存在しないパスに | codex=CLI_NOT_FOUND、他2者続行、partial | 全一致 |
| AT-14 | F12 | 入力 "日本語"、stub が 0xFF を出力 | 日本語は往復一致、0xFF は U+FFFD | 例外0件 |
| AT-15 | F10,F11 | 3 stub が stdin を読む | claude/codex は全文、agy は即EOF | ハングなし |
| AT-16 | F19 | (a)theme/意見×2/定型文を各上限で (b)定型文が TEMPLATE_MAX_CHARS+1 字で起動 | (a) R2プロンプト長 = W2 ≤ PROMPT_MAX_CHARS (b) 起動エラー | 実測一致 / 終了コード≠0 |
| AT-17 | F2,F8 | TIMEOUT_SEC=T_t, KILL_WAIT_SEC=K_t: (a)全stubハング (b)R1成功/R2ハング | (a) failed (b) partial | elapsed ≤ T_max(rounds_executed) |
| AT-18 | F6 | agy `.cmd` / `.exe` stub に "a<LF>b" | `.cmd`: argv は `a\nb`（2字）、`.exe`: 実改行を保持 | 受信文字列一致 |
| AT-19 | F9 | 各 error_code の ask_* と ok 結果、deliberate の ok/partial/failed | isError は ask_* で ok=false、deliberate で failed のみ true。起動前エラーは固定値 | 5.1 スキーマに適合 |
| AT-20 | F1,F2,F4,F14 | 競合: (a)空白のみ+BUSY (b)長すぎ+BUSY (c)BUSY+BIN未解決 (d)未解決+長すぎ (e)timeout+非0 (f)非0+空stdout | (a)INVALID_INPUT (b)PROMPT_TOO_LONG (c)BUSY (d)CLI_NOT_FOUND (e)TIMEOUT (f)NONZERO_EXIT | 5.3 の上位行 |
| AT-21 | F13 | 親環境に PYTHONUTF8 無し。Python 製 stub が "日本語" を print。(a)既定 CHILD_ENV_EXTRA (b)空文字に上書き | (a) stdout=="日本語" (b) 文字化け | (a)(b) の差 |
| AT-22 | F3 | stub が孫（長時間sleep）を起動してハング。(a)既定 TASKKILL_FLAGS (b)`/F` のみ | (a) 孫が tasklist に不在 (b) 孫が残存（対照。手動 kill） | (a)(b) の差 |
| AT-23 | F16,F17,F18 | stub が受信 argv を記録 | claude は `-p --permission-mode plan`、codex は `exec --sandbox read-only --skip-git-repo-check -` | 4 節の表と一致 |
| AT-24 | F21,F22,F23,F27 | (a)agy `.cmd` へ `%CD%` を含む prompt (b)R1意見に指示文を含め R2 (c)agy stub がファイル作成 (d)exit1 + stderr "auth expired" | (a) 展開後の値を受信 (b) `<opinion>` 内にそのまま渡る (c) changed、ファイルは残る (d) NONZERO_EXIT のみ | 7 節の記述と一致（F24〜F26, F28 は試験対象外） |

スコープ外: パッケージング/配布、CI、運用手順書、認証管理、ラウンド3の自動化、deliberate 以外のラウンド制御ツール、結果の永続化。
