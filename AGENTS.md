# AGENTS.md — Reason Network Chat

For coding agents. Read these rules first, then only the reference section needed for your task.
People start at [README.md](README.md); detailed controls are in the [user manual](docs/manual.md).

## Find the procedure

| Task | Read before acting |
|---|---|
| Install, verify and open the page | [Setup procedure](docs/reference/agent-operations.md#setup-procedure) |
| Start, restart, stop or adopt a worker | [Worker commands](docs/reference/agent-operations.md#starting-and-restarting-workers-agents-read-this) |
| Configure Codex speed | [Fast mode](docs/reference/agent-operations.md#codex-fast-mode) |
| Set up a persistent Gemini reviewer | [Gemini setup](docs/reference/agent-operations.md#gemini-reviewer-setup) |
| Start a message in a group room | [Room posting](docs/reference/agent-operations.md#starting-a-message-in-a-group-room-agents-read-this) |
| Change a request or setting | [Configuration and HTTP API](docs/reference/api.md) |
| Change relay, wake or process behavior | [Implementation contracts and pitfalls](docs/reference/internals.md) |

## Required operating rules

- Use `python rnc.py worker` for worker management. Never start `reason network serve` directly inside your turn:
  inherited output handles can prevent the turn from ending. Keep detached launches and file logs.
- Preserve existing workers and their settings. Inspect `worker list` and ownership proof before restarting or
  adopting anything. Do not infer ownership from a name, old log, or environment variable. Fail closed when
  process evidence is unavailable. A restart can discard a running turn; retain the busy-worker confirmation.
- Send only messages the user requested, or an approved test. New workers and optional round-trip tests take
  work as the user. Follow the setup procedure's checks and stop/report a failed check; the user signs in.
- Full access permits deletion, installation and network commands without approval, including work received
  from other agents. Keep the confirmation whenever it is chosen. Auto-wake and relays spend turns: preserve
  their limits, retry state and the user's opt-in. Never force a second writer into a locked Codex conversation.
- Post to rooms only as your own member through `rnc.py room send`. The server verifies process ancestry or an
  explicit `allowPost` exception. Environment variables are not identity proof; do not add an env shortcut.
- Gemini publishing must use its configured GitHub App identity. Never fall back to personal/Codex credentials
  or put tokens into model input. Verify author, inspected head and posted text; preserve cached results and
  deduplication. An uncertain model call pauses until explicit retry. See the linked setup procedure.

## Required implementation rules

- Never write Reason's database; use SQLite `mode=ro`. Bind only to `127.0.0.1`, with one server per port.
  Keep Host/Origin checks, POST tokens and frame protection. Treat message text as untrusted; HTML-escape it,
  validate link schemes and never turn page text into a shell command.
- Preserve room membership and recipient rules, deduplication, queued hand-offs and restart recovery. Do not
  relay worker failures as answers. Read the relevant implementation contract before changing these paths.
- Parse CLI JSON, not localized text output. Decode subprocess output as UTF-8. Keep Windows `.cmd`/`.bat`
  message-injection guards, native executable selection and child-session environment cleanup.
- Keep multilingual text in UTF-8 files. Never pipe non-ASCII Python source through an ASCII PowerShell pipe.
  Set both `$OutputEncoding` and `[Console]::OutputEncoding` when piping; `python -X utf8` cannot recover upstream
  loss. Before external posting run `python rnc.py text check --file body.md`, then compare the posted body with
  the original. Chat does not intercept an agent's independent `gh` commands.
- No dependencies or build step. Model/effort lists come from each agent's catalog, never a hard-coded list.
- Change the `API` constants in both `server.py` and `index.html` when request/response shapes change.
  Keep boot/token reload behavior; docs-only edits do not require an API bump.

## Documentation and validation

- Keep README focused on installation and first use. Put user controls in `docs/manual*.md`; agent procedures,
  API fields and implementation evidence belong in `docs/reference/`. Link instead of duplicating detail.
- User docs have English `X.md`, Korean `X.ko.md` and Chinese `X.zh-CN.md`, each with the language switcher.
  Update all three together. `AGENTS.md`, `CLAUDE.md` and agent-only technical references are English.
- UI strings belong in every `T` table (`ko`, `en`, `zh`) in `index.html`.
- Figures: edit `TEXT` in `docs/tools/make_figures.py`, run that script, and commit the SVGs. Never hand-edit SVGs.
- Every PR adds one row at the top of all three `patch_notes/README*.md` files: KST time, PR link, one sentence
  about the user-visible change. A new date starts a new `## YYYY-MM-DD` section.
- Run `python -m unittest discover tests` before a PR. For documentation moves, also check relative links,
  heading anchors and image paths, and measure before/after lengths. Do not claim runtime behavior from docs.
