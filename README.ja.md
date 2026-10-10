# AI-Gougi

[English](README.md) | 日本語

**Claude Code / Codex CLI / Antigravity CLI(`agy`) に同一テーマを諮り合議させる** MCP サーバーです。
各 CLI は単体のヘッドレス実行しか持たないため、AI-Gougi が各 CLI を subprocess でラップして MCP ツールとして公開します。司会は呼び出し側の Claude Code が担い、サーバー自身は司会をしません。

- Windows ネイティブ(`.cmd` shim 対応、`taskkill /T /F` でプロセスツリーを kill)
- 参加者はすべて**読み取り専用**で起動(claude: plan モード、codex: `--sandbox read-only`)
- 応答が数分かかるため長いタイムアウト(既定 1 回 10 分)。一部が失敗しても合議は続行
- Python + FastMCP(asyncio)、stdio トランスポート

## アーキテクチャ

```
Claude Code(司会/ラウンド3) --MCP stdio--> AI-Gougi (FastMCP, asyncio)
   ask_claude / ask_codex / ask_agy / deliberate
        |  run_cli(participant, prompt)  -- 唯一の subprocess 入口
        +--> claude | codex | agy   (cwd=WORKDIR, shell=False)
```

`deliberate` は最大 2 ラウンドを並列実行します。

1. **R1** – 全参加者がテーマに独立して意見を出す。
2. **R2** – R1 の成功者が他者の意見を受けて反論する。
3. **R3** – 呼び出し側(司会)が整理する。サーバーは担当しない。

## 必要環境

- Windows
- Python 3.10 以上
- Python パッケージ: `mcp`, `jsonschema`
- 参加者 CLI(`claude`, `codex`, `agy`)が導入・認証済みであること(`PATH` で解決。`AI_GOUGI_BIN_*` で上書き可)

```
pip install mcp jsonschema
```

## 使い方

```
python -m ai_gougi                 # MCP サーバー(stdio)として起動
python -m ai_gougi --check-config  # 設定を検査し、起動ログを stderr に出して終了コード 0 で終了
```

stdout は MCP 通信専用で、ログはすべて stderr(`[ai_gougi] <kind>: ...`)に出ます。

### Claude Code への登録

議論対象プロジェクトの `.mcp.json` の例です。`WORKDIR` の既定はサーバー起動時の cwd で、固定したい場合は `AI_GOUGI_WORKDIR` を指定します。

```json
{
  "mcpServers": {
    "ai-gougi": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "ai_gougi"],
      "env": {
        "PYTHONPATH": "D:/path/to/ai-gougi",
        "AI_GOUGI_WORKDIR": "D:/path/to/your/project"
      }
    }
  }
}
```

## MCP ツール

| ツール | 引数 | 説明 |
|---|---|---|
| `ask_claude` / `ask_codex` / `ask_agy` | `prompt`(string) | 参加者 1 名を 1 回実行し `AskResult` を返す |
| `deliberate` | `theme`(string), `rounds`(int, 任意, 1..2) | 全参加者へ並列に諮り(R1)、反論(R2)を行い `DeliberateOutput` を返す |

結果は `structuredContent` に入ります(`content` にも同じ JSON)。失敗時は `isError=true`。

- `AskResult`: `participant`, `ok`, `exit_code`, `stdout`, `stderr`, 切り詰め情報, `timed_out`, `duration_ms`, `workdir_check`(実行前後の WORKDIR スナップショット比較), `error_code`, `error_message`
- `DeliberateOutput`: `status`(`ok` / `partial` / `failed`), `error_code`, `rounds_requested`, `rounds_executed`, `skipped_reason`, `elapsed_ms`, `rounds[]`

エラーコード: `INVALID_INPUT`, `PROMPT_TOO_LONG`, `THEME_TOO_LONG`, `CMDLINE_TOO_LONG`(agy のみ), `CLI_NOT_FOUND`, `SPAWN_FAILED`, `TIMEOUT`, `NONZERO_EXIT`, `EMPTY_OUTPUT`, `BUSY`, `ALL_FAILED`。

## 設定

全設定は環境変数 `AI_GOUGI_<名前>` で上書きできます。主なもの:

| 名前 | 既定値 | 説明 |
|---|---|---|
| `WORKDIR` | 起動時 cwd | 子プロセスの cwd・スナップショット対象 |
| `BIN_claude` / `BIN_codex` / `BIN_agy` | `claude` / `codex` / `agy` | 実行ファイル(`PATH` 解決) |
| `TIMEOUT_SEC` | 600 | CLI 1 回の実行上限 |
| `PROMPT_MAX_CHARS` | 7000 | `prompt` の上限 |
| `THEME_MAX_CHARS` | 1500 | `theme` の上限 |
| `OUTPUT_MAX_CHARS` | 20000 | stdout 切り詰め上限(先頭を残す) |
| `STDERR_MAX_CHARS` | 4000 | stderr 切り詰め上限(末尾を残す) |
| `MAX_CONCURRENT_PROCS` | 3 | 同時子プロセス数 |
| `PARTICIPANT_ORDER` | `claude,codex,agy` | `deliberate` の参加者順 |

全項目は [docs/ai-gougi-usage.md](docs/ai-gougi-usage.md) を参照してください。

## テスト

実 CLI は呼ばず、`tests/stubs/` の stub CLI を使います。

```
python -m pytest -q --strict-markers
```

## ドキュメント

- [docs/design-ai-gougi.md](docs/design-ai-gougi.md) – 設計書
- [docs/ai-gougi-usage.md](docs/ai-gougi-usage.md) – 利用ガイド

## ライセンス

[MIT](LICENSE)
