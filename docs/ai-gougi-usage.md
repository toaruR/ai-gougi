# AI-Gougi 利用ガイド

実装(`ai_gougi/`)に基づく公開インターフェースの説明。設計は `docs/design-ai-gougi.md` を参照。

## 1. 起動

```
python -m ai_gougi                 # MCP サーバ(stdio)として起動
python -m ai_gougi --check-config  # 定型文長を検査し、起動ログ(stderr)を出して終了コード0で終了
```

- 起動時に `check_template` が定型文+ラベル長を検査し、`TEMPLATE_MAX_CHARS` 超過なら stderr にメッセージを出して終了コード1で終了する。
- WORKDIR(起動時 cwd の絶対パス、または `AI_GOUGI_WORKDIR`)が git 管理外の場合は stderr に警告1行を出す(codex は `--skip-git-repo-check` 付きで起動)。
- stdout は MCP の stdio 通信専用。ログはすべて stderr(`[ai_gougi] <kind>: ...`)。

## 2. MCP ツール

サーバ名は `ai-gougi`。各ツールは `structuredContent` に結果 JSON を持ち、本文(`content`)には同じ JSON 文字列を返す。
失敗時は `isError=true`(ask系は `ok == false`、deliberate は `status == "failed"`)。

### ask_claude / ask_codex / ask_agy

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| prompt | string | 必須 | 空白のみは INVALID_INPUT。`PROMPT_MAX_CHARS` 超は PROMPT_TOO_LONG |

起動方法:
- claude: `<exe> -p --permission-mode plan`(プロンプトは stdin)
- codex: `<exe> exec --sandbox read-only --skip-git-repo-check -`(プロンプトは stdin)
- agy: `<exe> -p <prompt>`(コマンドライン渡し、stdin は DEVNULL。改行は拡張子に応じて変換)

結果(AskResult。全キー必須、追加キー不可):

| キー | 型 | 説明 |
|---|---|---|
| participant | "claude"/"codex"/"agy" | |
| ok | bool | タイムアウトなし かつ exit 0 かつ stdout が空白でない |
| exit_code | int/null | 起動前エラー・SPAWN_FAILED は null |
| stdout / stderr | string | 切詰め後。stdout は先頭 `OUTPUT_MAX_CHARS` 字、stderr は末尾 `STDERR_MAX_CHARS` 字 |
| stdout_total_chars / stderr_total_chars | int | 切詰め前の文字数 |
| stdout_truncated / stderr_truncated | bool | |
| timed_out | bool | |
| duration_ms | int | |
| workdir_check | "unchanged"/"changed"/"skipped" | 実行前後の WORKDIR スナップショット比較 |
| error_code | string/null | ok=true なら null、ok=false なら文字列(下記) |
| error_message | string/null | error_code が null のときのみ null |

### deliberate

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| theme | string | 必須 | 空白のみは INVALID_INPUT。`THEME_MAX_CHARS` 超は THEME_TOO_LONG |
| rounds | integer | 任意 | 省略時 `DEFAULT_ROUNDS`。範囲 1..`MAX_ROUNDS`、範囲外・bool は INVALID_INPUT |

動作: 全参加者(`PARTICIPANT_ORDER` 順の claude, codex, agy)へ並列でテーマを諮る(R1)。rounds>=2 のとき R1 成功者のみが他者の意見(各 `OPINION_MAX_CHARS` に切詰め)を受けて反論する(R2)。整理は呼び出し側が行う。処理は先に参加者数ぶんの枠を一括予約し、確保できなければ BUSY。

結果(DeliberateOutput):

| キー | 型 | 説明 |
|---|---|---|
| status | "ok"/"partial"/"failed" | |
| error_code | string/null | INVALID_INPUT / THEME_TOO_LONG / BUSY / ALL_FAILED / null |
| error_message | string/null | |
| rounds_requested | int | 入力不正時は 0 の場合あり |
| rounds_executed | int | |
| skipped_reason | "S1_BELOW_MIN"/null | R1 成功数が `MIN_SUCCESS_R2` 未満で R2 を省略したとき |
| elapsed_ms | int | |
| rounds | array | `{round: int>=1, results: [AskResult...]}` |

status 判定: R1 全員失敗 = failed(ALL_FAILED)。要求ラウンドを全て実行し全結果が ok = ok。それ以外(R2 省略・一部失敗)= partial。

## 3. エラーコード

AskResult.error_code: `INVALID_INPUT`, `PROMPT_TOO_LONG`, `CMDLINE_TOO_LONG`(agy のみ), `CLI_NOT_FOUND`, `SPAWN_FAILED`, `TIMEOUT`, `NONZERO_EXIT`, `EMPTY_OUTPUT`, `BUSY`。

- 起動前の検証順: INVALID_INPUT -> PROMPT_TOO_LONG -> BUSY -> CLI_NOT_FOUND -> CMDLINE_TOO_LONG。起動前エラーは `exit_code=null`, `workdir_check="skipped"`、文字列空、数値0。
- TIMEOUT: `TIMEOUT_SEC` 超過でプロセスツリーを kill(Windows は `taskkill /T /F`)。部分出力は保持される。
- NONZERO_EXIT: exit code != 0。EMPTY_OUTPUT: exit 0 だが stdout が空白のみ。

DeliberateOutput.error_code: `INVALID_INPUT`, `THEME_TOO_LONG`, `BUSY`, `ALL_FAILED`。

## 4. 環境変数(既定値は ai_gougi/config.py)

全項目は `AI_GOUGI_<名前>` で上書き可能。呼び出しごとに読むのでキャッシュされない。整数項目に変換不能な値を与えると `ValueError`。
タプル項目はカンマ区切り。

| 名前 | 既定値 | 説明 |
|---|---|---|
| WORKDIR | 起動時 cwd の絶対パス | 子プロセス cwd・スナップショット対象 |
| BIN_claude / BIN_codex / BIN_agy | claude / codex / agy | 実行ファイル(PATH 解決) |
| TIMEOUT_SEC | 600 | 1回の CLI 実行の上限 |
| KILL_WAIT_SEC | 5 | kill 後のパイプ閉鎖待ち |
| TASKKILL_FLAGS | `/T /F` | Windows の taskkill 引数 |
| CHILD_ENV_EXTRA | `PYTHONUTF8=1` | 子プロセスへ追加する環境変数(`K=V,K2=V2`)。空文字で無効 |
| ENCODING | utf-8 | stdin/stdout のエンコーディング |
| PROMPT_MAX_CHARS | 7000 | ask の prompt 上限 |
| CMDLINE_MAX_CHARS | 8000 | agy コマンドライン長の上限 |
| AGY_EXE_LEN_REF | 38 | N_safe/x_lim 計算で使う agy 実行ファイル長の基準 |
| CMDLINE_FIXED_CHARS | 6 | コマンドライン固定部の長さ |
| THEME_MAX_CHARS | 1500 | deliberate の theme 上限 |
| OPINION_MAX_CHARS | 2000 | R2 に渡す他者意見の上限(超過分は先頭 `OPINION_MAX_CHARS - MARKER_RESERVE` 字+マーカー) |
| MARKER_FORMAT | `\n…[省略 {k} 文字]` | 省略マーカー書式 |
| MARKER_RESERVE | 20 | マーカー予約長 |
| TEMPLATE_MAX_CHARS | 500 | R2 定型文+ラベルの上限(起動時検査) |
| OUTPUT_MAX_CHARS | 20000 | stdout 切詰め上限 |
| STDERR_MAX_CHARS | 4000 | stderr 切詰め上限 |
| MIN_SUCCESS_R2 | 2 | R2 を実行するのに必要な R1 成功数 |
| DEFAULT_ROUNDS | 2 | deliberate の rounds 既定 |
| MAX_ROUNDS | 2 | rounds 上限 |
| MAX_CONCURRENT_PROCS | 3 | 同時子プロセス数(枠) |
| SNAPSHOT_MAX_FILES | 5000 | スナップショット対象の最大ファイル数 |
| SNAPSHOT_EXCLUDE | `.git,node_modules` | スナップショット除外 |
| PARTICIPANT_ORDER | `claude,codex,agy` | deliberate の並び順 |

導出関数(`ai_gougi.config`): `period()` = TIMEOUT_SEC+KILL_WAIT_SEC (既定605)、`t_max(r)` = r×P (1..MAX_ROUNDS 外は ValueError)、`keep()`、`w2()`、`n_safe()`、`x_lim(n0)`、`return_cap()` = 参加者数×MAX_ROUNDS×(OUTPUT+STDERR) (既定144000)。

## 5. テスト実行

実 CLI は呼ばない。`tests/stubs/` の stub CLI(`.cmd` shim 経由で `AI_GOUGI_BIN_*` を差し替え)を使う。

```
python -m pytest -q --strict-markers      # 全スイート(約90秒、153件)
python -m pytest tests/test_config.py -q  # 個別
```

marker `at`(`tests/conftest.py` で登録)は受入試験 AT-nn との対応付けに使う。

## 6. 既知の計画上の欠陥・補足

- T006 の負例 verify: `ai_gougi.schema.SCHEMA` は設計書5.1ブロック(`DESIGN_SCHEMA`)に最上位 `"$ref": "#/$defs/AskResult"` だけを加えたもの。`Draft202012Validator(SCHEMA)` が AskResult 検証になり、負例は不変条件違反で exit 1 になる。`validate()` は独自の `$ref` ラッパーを使うため影響なし。`test_schema_equals_design_block` は `DESIGN_SCHEMA == 設計書ブロック`、`SCHEMA` から `$ref` を除いたものがブロックと等価、かつ追加 `$ref` がちょうど上記であることを検査する。
- T008/T027 の `import tests.stubs.make_stubs` / `from tests.coverage_map import check`: site-packages の別 `tests` に遮蔽されていたため `tests/__init__.py` を追加し、リポジトリ直下から実行すれば自パッケージが解決される。これに伴い tests 内の `import probe_gate` / `from coverage_map import` は `from tests import probe_gate` / `from tests.coverage_map import` に変更(検査内容は不変)。T027 負例 `check(drop='AT-07')` は検出(問題数1)により exit 1 になる。
- コミットベース verify(`check_task_commit.py Txxx --green/--revert-check`)の代替: 作業ツリーのみのため `.strict-goal/scratch/wt_check.py` でタスクの変更ファイル存在確認・自タスクのテスト・全スイート green と、葉タスクのみ pristine コピーで追加ファイルを削除した revert 相当(非葉は対象外)を検査し、結果を `.strict-goal/scratch/wt_check.out` に出力する。T001/T002 の `git log` 検査はファイル存在確認で代替。
- テスト弱体化なしの確認: `.strict-goal/scratch/cmp_tests.py` が baseline との差分を `test_diffs/` に出し、テスト関数数と assert 数が減っていないことを検査する。
- `scripts/check_task_commit.py` を使う verify はタスクごとのコミットを前提とするが、タスク単位のコミットは作成されていないため通らない。
- 後続課題: T016 の定型文長(`TEMPLATE_MAX_CHARS`=500 ちょうどに合わせた補足文 `_FILLER` による調整)の見直し、T023 の `stub_run`(`tests/stubs/stub_run.py`)に関する整理。
- T001/T002 の verify(`subprocess.check_output(['git','log','--format=%s'],text=True)`)は、既定の cp932 ロケールでは UTF-8 の日本語 subject を正しくデコードできない。このリポジトリのみで `git config --local i18n.logOutputEncoding cp932` を設定してから実行する(グローバル設定や `PYTHONUTF8` は変更しない)。
