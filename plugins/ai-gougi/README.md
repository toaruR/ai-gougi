# AI-Gougi 合議スキル

Agent Plugins Specification **1.0.0** に準拠するスキルパッケージ。
Claude CodeとCodexには同じ `skills/gougi/` を個人スキルとして配置できる。

```text
ai-gougi/
├── plugin.json
└── skills/
    └── gougi/
        ├── SKILL.md
        └── agents/openai.yaml
```

## 前提

AI-Gougi MCPの `deliberate` が対象チャットで利用できること。
このパッケージが提供するコンポーネントはスキルで、MCP接続はクライアントで別途設定する。
MCP登録後は、接続時にクライアントがサーバーを自動起動する。
既定の2ラウンドでは、クライアントのツール待ち時間を1300秒以上に設定する。
ローカルstdioサーバーの利用可否は実行環境に依存し、クラウドのチャットへローカル設定が自動共有されるわけではない。

## インストール方法

このREADMEと `plugin.json` があるディレクトリで、以下のPowerShellを実行します。
リポジトリを取得した場合は、先に `plugins/ai-gougi/` へ移動してください。
配布ZIPを展開した場合は、展開先で実行できます。

```powershell
$gougiSource = Join-Path (Get-Location).Path 'skills\gougi'
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

片方だけに導入する場合は、そのクライアントの `Copy-Item` 行だけ実行します。
導入後は新しいセッションを開いてスキルを確認してください。
MCP接続の登録方法は以下を参照してください。

### Claude Code

`skills/gougi/` を `~/.claude/skills/gougi/` にコピーする。

```text
/gougi この設計の妥当性と改善点を検討して
```

Claude CodeでのMCP登録例（Python 3.10以上と `mcp==1.26.0` が必要）:

```text
claude mcp add ai-gougi --scope user --env PYTHONPATH=/path/to/ai-gougi PYTHONUTF8=1 -- /path/to/venv/python -m ai_gougi
```

Windowsでは仮想環境のPythonは `/path/to/venv/Scripts/python.exe`。
サーバーの作業ディレクトリを固定しなければ、起動元プロジェクトを引き継ぐ。
接続を登録した後は、新しいセッションで `/mcp` と `/gougi` を確認する。

### Codex

`skills/gougi/` を `~/.codex/skills/gougi/` にコピーする。
`CODEX_HOME` を設定している場合は、そのディレクトリの `skills/gougi/` を使う。

```text
$gougi この設計の妥当性と改善点を検討して
```

グローバルMCP設定の `tool_timeout_sec` は1300秒以上にする。
スキルの検出は新しいチャットで確認する。

## Agent Plugins対応クライアント

このディレクトリをプラグインのルートとして、対象クライアントの導入手順で登録する。
`plugin.json` の `$schema` が規格バージョンを指定し、スキルは固定位置 `skills/gougi/SKILL.md` から検出される。
コマンド名や名前空間はホストが定めるため、そのクライアントのスキル一覧から `gougi` を選ぶ。

Claude Codeのネイティブプラグイン形式とAgent Plugins形式は異なる。
Claude Codeでは上記の個人スキル配置で利用する。

## 使い方

| クライアント | 入力例 |
|---|---|
| Claude Code | `/gougi この設計の妥当性と改善点を検討して` |
| Codex | `$gougi この設計の妥当性と改善点を検討して` |

独立意見だけを集めたい場合は、`/gougi 独立意見だけで、3モジュールを段階移行する是非を検討して` と指定する。
Codexでは先頭を `$gougi` に置き換える。

通常は `deliberate(theme=依頼内容, rounds=2)` を1回呼ぶ。
独立意見だけを依頼した場合は `rounds=1`。
R1・R2の実行後、司会が共通点・対立点・推奨案を整理する。
部分失敗とR2省略を明示し、MCP未接続や全員失敗を合議成功として扱わない。

## 中間生成物・最終成果物の出力先

| 生成物 | 出力先 |
|---|---|
| 中間生成物：各参加者のR1・R2の回答 | MCPの返却JSON内の `structuredContent.rounds[].results[].stdout`。R2省略時はR1のみ |
| エラー・実行情報 | `structuredContent.rounds[].results[]` 内の `stderr`、`error_code` など |
| 最終成果物：共通点・対立点・推奨案 | 呼び出し側クライアントのチャット回答 |

同じ結果JSONはMCPの `content` にも含まれる。
中間結果はメモリ内で保持し、ツール完了時に返す。
現在のサーバーとラッパーには、固定の出力フォルダーや結果の自動ファイル保存はない。
ファイルとして残す場合は、呼び出し側クライアントに保存先を指定して別途保存を依頼する。
`WORKDIR` は参加者CLIの作業と変更検査の対象フォルダー。

## 仕様の根拠

- [Agent Plugins 1.0.0](https://agent-plugins.org/specification): root `plugin.json` と固定位置のコンポーネント。
- [Agent Skills](https://agentskills.io/specification): 共通 `SKILL.md` の書式。
- [Claude Code Skills](https://code.claude.com/docs/en/skills): 個人スキルと `/gougi` 形式の呼び出し。
