# AI-Gougi

English | [日本語](README.ja.md)

An MCP server that lets **Claude Code, Codex CLI, and Antigravity CLI (`agy`) deliberate on the same topic**.
Each CLI only offers single-shot headless execution, so AI-Gougi ("gougi" = council deliberation) wraps them as subprocesses and exposes them as MCP tools. The calling client, such as Claude Code or Codex, acts as the moderator; the server itself never moderates.

- Windows native (`.cmd` shims, `taskkill /T /F` process-tree kill)
- All participants run **read-only** (claude: plan mode, codex: `--sandbox read-only`)
- Long timeouts (10 min per call by default); partial failures do not abort a deliberation
- Built with Python + FastMCP (asyncio), stdio transport

## Architecture

```
Claude Code (moderator / round 3) --MCP stdio--> AI-Gougi (FastMCP, asyncio)
   ask_claude / ask_codex / ask_agy / deliberate
        |  run_cli(participant, prompt)  -- the only subprocess entry point
        +--> claude | codex | agy   (cwd=WORKDIR, shell=False)
```

`deliberate` runs up to two rounds in parallel:

1. **R1** – every participant gives an independent opinion on the theme.
2. **R2** – participants that succeeded in R1 read the other opinions and rebut them.
3. **R3** – the caller (moderator) summarizes. Not done by the server.

## Requirements

- Windows
- Python 3.10+
- Python packages: `mcp`, `jsonschema`
- The participant CLIs installed and authenticated: `claude`, `codex`, `agy` (resolved via `PATH`, or override with `AI_GOUGI_BIN_*`)

```
pip install mcp jsonschema
```

## Usage

After the MCP server is registered, your client starts it automatically when connecting. Follow the client registration and wrapper skill installation steps below.

### Registering with Claude Code

Example `.mcp.json` in the project to be discussed. `WORKDIR` defaults to the server's startup cwd; set `AI_GOUGI_WORKDIR` to pin it.

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

### Registering with Codex

Add the following to `~/.codex/config.toml` (`$CODEX_HOME/config.toml` if `CODEX_HOME` is set). Replace the example path with your AI-Gougi checkout, and use a Python executable with the required packages installed.

```toml
[mcp_servers.ai-gougi]
command = "python"
args = ["-m", "ai_gougi"]
tool_timeout_sec = 1300

[mcp_servers.ai-gougi.env]
PYTHONPATH = "/path/to/ai-gougi"
PYTHONUTF8 = "1"
```

### Installing the `gougi` wrapper skill

The wrapper calls `deliberate` and asks the calling client to summarize the results. First register the AI-Gougi MCP server with your client; copying the skill does not register the server. Allow at least 1300 seconds per tool call for the default two rounds.

Run this PowerShell snippet from the repository root to install the skill globally for both Claude Code and Codex:

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

This creates `~/.claude/skills/gougi/` and `~/.codex/skills/gougi/` (or `$CODEX_HOME/skills/gougi/`). To install for just one client, run only its copy command. Open a new session after installing; in Claude Code, use `/mcp` to check that AI-Gougi is connected.

The [wrapper package](plugins/ai-gougi/README.md) follows Agent Plugins Specification 1.0.0. Compatible clients can register `plugins/ai-gougi/` as the plugin root and discover `gougi` under `skills/`; invocation names depend on the client.

### Using the wrapper

| Client | Input |
|---|---|
| Claude Code | `/gougi Review this design and suggest improvements` |
| Codex | `$gougi Review this design and suggest improvements` |

By default, the wrapper runs independent opinions (R1) and rebuttal/reconsideration (R2), then the caller summarizes common ground, disagreements, and a recommendation. It reports participant failures and skipped rounds.

To request independent opinions only:

```text
/gougi Give independent opinions only on whether to migrate these three modules incrementally
```

Use `$gougi` instead in Codex. Provide the target file or relevant background when the topic depends on context; participant CLIs do not receive the caller's conversation history. If the MCP tool is unavailable, the skill reports the missing connection rather than producing a deliberation result.

### Output locations

| Artifact | Output location |
|---|---|
| Intermediate results: R1 independent opinions | The MCP response: `structuredContent.rounds[0].results[].stdout` |
| Intermediate results: R2 rebuttals and reconsideration | The MCP response: `structuredContent.rounds[1].results[].stdout`, when R2 runs |
| Participant errors and execution details | Each result's `stderr`, `error_code`, and other fields in `structuredContent.rounds[].results[]` |
| Final result: the moderator's common ground, disagreements, and recommendation | The calling client's chat response |
| Deliberation record: conclusion, metadata, and all responses | `docs/gougi/YYYY-MM-DD-<slug>.md` in the working project (when using the gougi skill) |
| Server diagnostic logs | The server's stderr, handled by the MCP client |

The same result JSON is also returned in MCP `content`. Round results are collected in memory and returned when the tool call completes; AI-Gougi does not stream or save them to intermediate files. The server and wrapper do not write files. When using the gougi skill, the moderator (the calling client) saves the deliberation record as Markdown. Specify another path along with the topic to change the location, or say not to save to skip the record. Nothing is saved when no participant succeeds. `WORKDIR` identifies the participant CLIs' working directory and the directory checked for changes.

## MCP tools

| Tool | Arguments | Description |
|---|---|---|
| `ask_claude` / `ask_codex` / `ask_agy` | `prompt` (string) | Run one participant once. Returns an `AskResult` |
| `deliberate` | `theme` (string), `rounds` (int, optional, 1..2) | Ask all participants in parallel (R1), then rebuttal (R2). Returns a `DeliberateOutput` |

Results are returned in `structuredContent` (the same JSON is also in `content`). On failure `isError=true`.

- `AskResult`: `participant`, `ok`, `exit_code`, `stdout`, `stderr`, truncation info, `timed_out`, `duration_ms`, `workdir_check` (WORKDIR snapshot comparison before/after), `error_code`, `error_message`
- `DeliberateOutput`: `status` (`ok` / `partial` / `failed`), `error_code`, `rounds_requested`, `rounds_executed`, `skipped_reason`, `elapsed_ms`, `rounds[]`

Error codes: `INVALID_INPUT`, `PROMPT_TOO_LONG`, `THEME_TOO_LONG`, `CMDLINE_TOO_LONG` (agy only), `CLI_NOT_FOUND`, `SPAWN_FAILED`, `TIMEOUT`, `NONZERO_EXIT`, `EMPTY_OUTPUT`, `BUSY`, `ALL_FAILED`.

## Configuration

Every setting can be overridden with an environment variable `AI_GOUGI_<NAME>`. Main ones:

| Name | Default | Description |
|---|---|---|
| `WORKDIR` | startup cwd | Child process cwd and snapshot target |
| `BIN_claude` / `BIN_codex` / `BIN_agy` | `claude` / `codex` / `agy` | Executables (resolved via `PATH`) |
| `TIMEOUT_SEC` | 600 | Limit per CLI run |
| `PROMPT_MAX_CHARS` | 7000 | Max `prompt` length |
| `THEME_MAX_CHARS` | 1500 | Max `theme` length |
| `OUTPUT_MAX_CHARS` | 20000 | stdout truncation limit (keeps head) |
| `STDERR_MAX_CHARS` | 4000 | stderr truncation limit (keeps tail) |
| `MAX_CONCURRENT_PROCS` | 3 | Concurrent child processes |
| `PARTICIPANT_ORDER` | `claude,codex,agy` | Participant order in `deliberate` |

See [docs/ai-gougi-usage.md](docs/ai-gougi-usage.md) for the full list (Japanese).

## Tests

Tests never call the real CLIs; they use stub CLIs under `tests/stubs/`.

```
python -m pytest -q --strict-markers
```

## Documentation

- [docs/design-ai-gougi.md](docs/design-ai-gougi.md) – design document (Japanese)
- [docs/ai-gougi-usage.md](docs/ai-gougi-usage.md) – usage guide (Japanese)

## License

[MIT](LICENSE)
