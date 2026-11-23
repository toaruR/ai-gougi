<!-- knowledge-kit:begin section=general-instructions version=1.16.4 -->
## Communication Style
- Use Caveman mode.
- Drop filler words, preambles, and recaps.
- Be extremely concise. Keep explanations under 2 sentences.
- Full code, minimal chatter.

## ドキュメント配置ルール
`docs/` には次の置き場以外にファイルを作らない(ルールの実体: `docs/.docs-policy.json`。整理は `/docs-tidy`)。

| 置き場 | 中身 | frontmatter の type |
|---|---|---|
| `docs/spec/` | 今どうなっているか(仕様・アーキ・設計)。書き換えて最新に保つ | `spec` |
| `docs/decisions/` | なぜそう決めたか(ADR)。書いたら変えない | `decision` |
| `docs/research/` | 調査・比較・ベンチ。`YYYY-MM-DD-slug.md` | `research` |
| `docs/guides/` | 人間向けの説明・手順・原理解説 | `guide` |
| `docs/plans/` | 計画(plan モードの成果物を含む)。`YYYY-MM-DD-slug.md`。終わったら `plans/archive/` | `plan` |
| `docs/assets/` | 画像 | — |
| `docs/exports/` | html / pdf / pptx などの派生物(正本と同じ相対パス) | — |

- `.md` の先頭に frontmatter(`type`、plan/decision は `status: draft|active|done|superseded`、`owner: ai|human`)を付ける。日付は書かない(git から分かる)。
- ファイル名は英小文字・数字・ハイフンの kebab-case。日付付きの複製(`xxx_20261015.md` 等)は作らず、元のファイルを直接更新する。
- 新しいファイルを作る前に、既存ファイルへの追記で済まないか検討する。
- ビルド・変換の作業ファイルは `docs/` の外(`.cache/` 等)に置き、最終成果物だけを `docs/exports/` に置く。

## 返信の言語
最終的な返信は日本語で出力する。

## コード検索の指示方針
- コードベースの機能調査やコード探索を行う際は、最初に MCP ツール `search` (BM25 Code Search) を優先して使用してください。
- **Claude Code での呼び出し手順**: Claude Code では MCP ツールが Deferred Tool となるため、初回呼び出し前に必ず `ToolSearch` (`select:mcp__bm25-code-search__search`) でスキーマをロードしてから `mcp__bm25-code-search__search` を実行してください。
- `search` で結果が得られない場合、または特定のシンボル名の完全一致を直接検索する場合にのみ `grep_search` や `glob` を使用してください。

## Strict-Goal & Subagents Protocol
The following protocol applies **ONLY during `strict-goal` workflows** (e.g., requests matching `strict-goal [design|plan|implement]` or within an active rubric loop). For standard non-strict-goal requests, execute directly as usual.
- **Parent Role (Zero Direct Work)**: In strict-goal sessions, the parent agent acts strictly as a lightweight dispatcher. MUST NOT perform drafting, testing, hash calculation, scoring, or exploratory scripts directly to prevent $\mathcal{O}(T^2)$ token explosion.
- **Subagent Delegation Matrix** (subagents defined under `.claude/agents/`, launch via `Agent(subagent_type="<name>", prompt=...)`):
  - `sg-designer`: In-loop design supervisor (FSM lifecycle, external CLI / autonomous draft coordination, verifier scoring).
  - `sg-worker`: Draft & modify code/docs across all phases (`design`, `plan`, `implement`).
  - `sg-verifier`: Ephemeral verification, test execution, evidence extraction, and score submission.
  - `sg-scout`: Ephemeral codebase exploration (stateless inspection without context pollution).
  - `sg-implementer`: In-loop implementation supervisor (session lifecycle & worker coordination).
  - `sg-coder`: Standalone autonomous executor for smaller self-contained goals.
- **State Externalization**: NEVER trace back through chat history. Determine state and next action solely from bounded triplet $(P, \Sigma_t, O_t)$ via `loop_state(projection: "skill_state")`.
- **Autonomous Scope Selection**: On `strict-goal design`, select rubric at `loop_open` based on prompt boundaries: generic `design` (8 criteria) for software/classes, or `design.harness` (18 criteria) for agent/harness infrastructure.
<!-- knowledge-kit:end section=general-instructions -->

<!-- knowledge-kit:begin section=recording-rules version=1.16.4 -->
## 知見の記録ルール

**作業中に重要な知見を発見したら、ユーザーの指示を待たず自動で記録すること。**

| 種類 | 記録先 | 例 |
|---|---|---|
| また踏むバグ・罠 | `CLAUDE.md` の「ハマりポイント」に追記 | 設定ミス・バージョン固有の挙動 |
| 仕様・設計の理解 | `docs/` の該当ファイルに追記 | ライブラリの挙動・APIの仕様・設計意図 |
| 一時的な作業メモ | memory/ に project タイプで記録 | 調査中の状況・次回引き継ぎ事項 |

記録したら「〇〇をハマりポイントに追記しました」と一言報告する。
<!-- knowledge-kit:end section=recording-rules -->

<!-- knowledge-kit:begin section=gotchas version=1.16.4 -->
## ハマりポイント

<!--
書き方のルール（このコメントは残してよい）:
- 1項目 = 1箇条書き。先頭を **太字** で「何が起きるか／何に注意するか」を要約する
- 対処法・原因まで1項目内に書き切る。長くなる場合は docs/ に本文を移し、
  「（詳細: `@docs/xxx.md`）」と参照だけ残す
- 誤りと判明した項目は消すのではなく「以前〜と書いていたのは誤り」と経緯ごと訂正する
  （同じ早合点を繰り返さないため）
- 定期的な整理（重複統合・陳腐化検出・docs への分割・簡潔化）は /spec-doc が行う
-->

- （ここに知見を追記していく）
- **rtk フック経由の pytest は出力が壊れる**: `rtk proxy python -m pytest ...` で実行すること。
- **`import tests.*` が site-packages の別 `tests` に隠される**: `tests/__init__.py` 必須。→ 詳細: @docs/guides/ai-gougi-usage.md §6
- **日本語コミット件名の `git log` を Python(cp932)で読むと UnicodeDecodeError**: `git config --local i18n.logOutputEncoding cp932` で回避（PYTHONUTF8=1 は tasklist デコードを壊すので不可）。→ 詳細: @docs/guides/ai-gougi-usage.md §6
<!-- knowledge-kit:end section=gotchas -->
