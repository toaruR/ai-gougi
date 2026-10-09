# AI-Gougi（マルチAI合議MCPサーバー）

## 目的
テーマを与えると、Claude Code / Codex CLI / Antigravity CLI(agy) の3者が意見を出し合い、
合議して結論をまとめる仕組みを作りたい。司会役はClaude Code（このセッション）とする。

## 方針（決定済み）
- Python + FastMCP で自作MCPサーバー「AI-Gougi」を作る
- 公開ツール：ask_claude / ask_codex / ask_agy
  - 中身は各CLIのヘッドレス実行をsubprocessでラップ
    - claude -p "<prompt>" --permission-mode plan
    - codex exec --sandbox read-only "<prompt>"
    - agy -p "<prompt>"
- 合議の流れ（ラウンド制）
  1. 3者に同じテーマを独立に投げ、並列で意見取得
  2. 他2者の意見を添えて反論・修正点を求める
  3. 司会が一致点・相違点を整理して結論をまとめる
- 将来的にはラウンド制御そのものもツール化（例：deliberate(theme, rounds)）したい

## 制約・注意点
- 環境はWindows ネイティブ
- agy は --cwd が効かないため、subprocessのcwd引数で作業ディレクトリを固定する
- 3者とも書き込み不可（読み取り専用）で動かす。議論中にファイルを変更させない
- 応答に数分かかるのでタイムアウトは長め（10分程度）、ラウンド1は並列実行
- 標準エラー出力・終了コードも返し、失敗した参加者がいても合議は続行できるようにする
