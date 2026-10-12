# AI-Gougi

[English](README.md) | 日本語

**Claude Code / Codex CLI / Antigravity CLI(`agy`) に同一テーマを諮り合議させる** MCP サーバーです。
各 CLI は単体のヘッドレス実行しか持たないため、AI-Gougi が各 CLI を subprocess でラップして MCP ツールとして公開します。司会は呼び出し側の Claude Code や Codex が担い、サーバー自身は司会をしません。

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

MCPを登録すると、接続時にクライアントがサーバーを自動起動します。以下のクライアント登録とラッパースキルの導入を行ってください。

### Claude Code への登録

議論対象プロジェクトの `.mcp.json` の例です。`WORKDIR` の既定はサーバー起動時の cwd で、固定したい場合は `AI_GOUGI_WORKDIR` を指定します。

```json
{
  "mcpServers": {
    "ai-gougi": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "ai_gougi"],
      "timeout": 1300000,
      "env": {
        "PYTHONPATH": "D:/path/to/ai-gougi",
        "AI_GOUGI_WORKDIR": "D:/path/to/your/project"
      }
    }
  }
}
```

### Codexへの登録

以下を `~/.codex/config.toml` に追加します（`CODEX_HOME` を設定している場合は `$CODEX_HOME/config.toml`）。パスはAI-Gougiを配置した場所に置き換え、必要なパッケージが入ったPythonを指定してください。

```toml
[mcp_servers.ai-gougi]
command = "python"
args = ["-m", "ai_gougi"]
tool_timeout_sec = 1300

[mcp_servers.ai-gougi.env]
PYTHONPATH = "/path/to/ai-gougi"
PYTHONUTF8 = "1"
```

### ラッパースキル `gougi` のインストール方法

ラッパーは `deliberate` を呼び出し、呼び出し側が結果を整理するためのスキルです。先に各クライアントへAI-Gougi MCPを登録してください。スキルのコピーだけではMCP接続は登録されません。既定の2ラウンドを待てるよう、ツール待ち時間は1300秒以上にします。

リポジトリのルートで以下のPowerShellを実行すると、Claude CodeとCodexの両方へグローバルにインストールできます。

```powershell
$gougiSource = Join-Path (Get-Location).Path 'plugins\ai-gougi\skills\gougi'
$gougiClaudeSkills = Join-Path $env:USERPROFILE '.claude\skills'
$gougiCodexSkills = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $env:USERPROFILE '.codex\skills'
}
New-Item -ItemType Directory -Force -Path $gougiClaudeSkills, $gougiCodexSkills | Out-Null
Copy-Item -LiteralPath $gougiSource -Destination $gougiClaudeSkills -Recurse -Force
Copy-Item -LiteralPath $gougiSource -Destination $gougiCodexSkills -Recurse -Force
```

配置先は `~/.claude/skills/gougi/` と `~/.codex/skills/gougi/`（または `$CODEX_HOME/skills/gougi/`）です。片方だけに導入する場合は、そのクライアントの `Copy-Item` 行だけ実行してください。導入後は新しいセッションを開き、Claude Codeでは `/mcp` でAI-Gougiの接続も確認します。

[ラッパーのパッケージ](plugins/ai-gougi/README.md)はAgent Plugins Specification 1.0.0に準拠しています。対応クライアントでは `plugins/ai-gougi/` をプラグインのルートとして登録すると、`skills/` から `gougi` が検出されます。呼び出し名はクライアントのスキル一覧で確認してください。

### ラッパースキルの使い方

| クライアント | 入力例 |
|---|---|
| Claude Code | `/gougi この設計の妥当性と改善点を検討して` |
| Codex | `$gougi この設計の妥当性と改善点を検討して` |

既定では独立意見（R1）と反論・再検討（R2）を実行し、司会が共通点・対立点・推奨案を整理します。参加者の失敗やラウンド省略も明記します。

独立意見だけを集めたい場合：

```text
/gougi 独立意見だけで、3モジュールを段階移行する是非を検討して
```

Codexでは先頭を `$gougi` に置き換えます。会話内の文脈が必要なテーマでは、対象ファイルや背景も示してください。参加者CLIには司会の会話履歴が渡りません。MCPツールが利用できない場合は、その旨を報告して終了します。

### 中間生成物・最終成果物の出力先

| 生成物 | 出力先 |
|---|---|
| 中間生成物：R1の独立意見 | MCPの返却JSON内の `structuredContent.rounds[0].results[].stdout` |
| 中間生成物：R2の反論・再検討 | R2実施時の `structuredContent.rounds[1].results[].stdout` |
| 各参加者のエラー・実行情報 | `structuredContent.rounds[].results[]` 内の `stderr`、`error_code` など |
| 最終成果物：司会が整理した共通点・対立点・推奨案 | 呼び出し側クライアントのチャット回答 |
| 合議記録：結論・メタ情報・全回答 | 作業中プロジェクトの `docs/gougi/YYYY-MM-DD-<slug>.md`(gougiスキル使用時) |
| サーバーの診断ログ | サーバーのstderr。MCPクライアント側で扱います |

MCPの `content` にも同じ結果JSONが返ります。ラウンドの結果はメモリ内で保持し、ツールの完了時にまとめて返すため、途中のファイル出力やストリーミングは行いません。サーバーとラッパーはファイルを保存しません。gougiスキル使用時は、司会(呼び出し側クライアント)が合議記録をMarkdownで保存します。保存先はテーマと一緒に指定して変更でき、「保存しない」と指定すると記録を作りません。成功回答がない場合も保存しません。`WORKDIR` は参加者CLIの作業と変更検査の対象フォルダーです。

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
