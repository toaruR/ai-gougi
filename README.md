# AI-Gougi

English | [日本語](README.ja.md)

An MCP server that lets **Claude Code, Codex CLI, and Antigravity CLI (`agy`) deliberate on the same topic**.
Each CLI only offers single-shot headless execution, so AI-Gougi ("gougi" = council deliberation) wraps them as subprocesses and exposes them as MCP tools. The calling Claude Code session acts as the moderator; the server itself never moderates.

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

```
python -m ai_gougi                 # start as an MCP server (stdio)
python -m ai_gougi --check-config  # validate config, print startup log to stderr, exit 0
```

stdout is reserved for MCP; all logs go to stderr (`[ai_gougi] <kind>: ...`).

### Registering with Claude Code

Example `.mcp.json` in the project to be discussed. `WORKDIR` defaults to the server's startup cwd; set `AI_GOUGI_WORKDIR` to pin it.

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
