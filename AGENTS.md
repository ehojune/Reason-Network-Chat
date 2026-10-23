# AGENTS.md — setting up and operating reason-chat

For coding agents. Your user pasted this repo's URL and asked you to set it up, or is working in this repo.
The README is for the human; this file has the procedure, checks, configuration and pitfalls.

## What it is

A local web page that shows Reason Network messages on this computer as a chat room, and sends messages.

| Part | Role |
|---|---|
| `server.py` | Python standard library HTTP server on `127.0.0.1:8765`. No dependencies. |
| `index.html` | The whole UI (one file, no build). Polls `/api/state` every 3 s. Strings in ko/en/zh. |
| `.claude/launch.json` | Lets the Claude desktop app start the server and show the page in its Browser pane. |
| `docs/tools/make_figures.py` | Regenerates every README figure. Never hand-edit the SVGs. |

## Setup procedure

Do these in order. Each step has a check; stop and tell the user when a check fails.

1. **Python 3.8+.** `python --version` (Windows may need `py -3 --version`).
2. **Reason Network is installed and signed in.**
   - `reason network who --all --json` exits 0 and prints JSON with a `sessions` array.
   - The database exists: `~/.reason/network/network.db`.
   - If either fails, the user must install Reason Network from <https://reasonmachines.com/network> and run `reason network`
     to sign in. Do not install it or sign in for them: it opens a browser sign-in.
   - On Windows the CLI is usually `%LOCALAPPDATA%\Reason\bin\reason.exe`, which `server.py` finds without PATH.
3. **Get the code.** Clone into a folder the user agrees to (default: `~/reason-chat`).
   `git clone https://github.com/ehojune/reason-chat`
4. **Start the server** as a background process from the repo folder: `python server.py`.
   It prints `reason-chat on http://127.0.0.1:8765`. It exits with a clear message if the database is missing.
5. **Verify.** `GET http://127.0.0.1:8765/api/state` returns JSON whose `sessions` is non-empty and `whoError` is `null`.
6. **Open the page.**
   - Claude desktop app (Code tab): if the session's working folder is the repo, use the bundled `.claude/launch.json`
     (`preview_start` with name `reason-chat`). Otherwise add this entry to the working folder's `.claude/launch.json`,
     with the absolute path to `server.py`:

     ```json
     { "name": "reason-chat", "runtimeExecutable": "python",
       "runtimeArgs": ["-X", "utf8", "/absolute/path/to/reason-chat/server.py"], "port": 8765 }
     ```

   - Anything else: open <http://127.0.0.1:8765> in a browser.
7. **Tell the user** the URL, how to stop the server, and the "Good to know" points from the README that apply.

Optional round-trip test, only with the user's OK (it starts a headless agent that takes work):
`reason network serve codex --name chat-codex`, send it a one-line message from the page, confirm the reply appears,
then stop the worker.

## Configuration

| Variable | Default | Use |
|---|---|---|
| `REASON_CHAT_PORT` | `8765` | Listening port. Also change `port` in `launch.json`. |
| `REASON_CHAT_DB` | `~/.reason/network/network.db` | Daemon database path. |
| `REASON_BIN` | `%LOCALAPPDATA%\Reason\bin\reason.exe` on Windows, else `reason` on PATH | The Reason CLI. |
| `NODE_EXTRA_CA_CERTS` | unset | Root CA file for TLS-inspecting corporate networks. The CLI (Bun) needs it there; inherited by subprocesses. |

## HTTP API

Both endpoints accept only `Host: 127.0.0.1:<port>` or `localhost:<port>` (DNS-rebinding guard).

- `GET /api/state` →
  `{team, me, sessions[], messages[], whoError, now}`.
  `me` is the address the page sends as (`<person>/terminal`).
  `sessions[]` = live entries from `who --all --json` (`address, name, agent, status, doing, cwd, tier, live: true`)
  plus addresses seen only in history (`status: "gone"`, `live: false`).
  `messages[]` = rows of the `messages` table ordered by `sent_at` (ms epoch).
- `POST /api/send` with `Content-Type: application/json` and `{to, body, fyi}` → runs
  `reason network send <to> <body> [--fyi]`. Returns `{ok, rc, out, err}`; HTTP 502 when the CLI fails.

## Data source

Read-only SQLite (`mode=ro` URI). Checked against Reason Network 0.12.10.

| Table | Columns used |
|---|---|
| `messages` | `id, sender, sender_agent, recipient, reply_to, body, wake, sent_at, read_at, held` |
| `sessions` | `name, agent, cwd, doing, tier` (only for sessions no longer in `who`) |

Live status (`busy`/`idle`/`offline`) is not in the database; it comes from `who --all --json`.
If a Reason update changes the schema, `/api/state` returns HTTP 500 with the SQLite error; adjust the two queries in `state()`.

## Pitfalls

- **Never write the database** or open it without `mode=ro`. The daemon owns it.
- **Keep the bind address `127.0.0.1`.** The page shows private message text and can send as the user.
- **Do not parse CLI text output.** On Korean/Chinese Windows the console code page (CP949, GBK) garbles it. Use `--json` or the database. Decode subprocess output as UTF-8.
- **Windows batch shims.** If `REASON_BIN` points at a `.cmd`/`.bat`, cmd.exe would re-parse message text (`&`, `|`, `%`). `server.py` refuses to start; point it at `reason.exe`.
- **Idle Codex app sessions** may leave a message unread until their next turn. Not a reason-chat bug. Workers from `reason network serve` answer at once.
- **`reason network serve codex` on Windows** can fail with "contains a cmd.exe special character" when a `codex.cmd` shim comes first on PATH. Put the folder of the real `codex.exe` first on PATH for that process.
- **Replies to `<person>/terminal`** stay unread in the database because nothing else reads that inbox. The page hides the read mark for them.
- **Sending is acting for the user.** Send only what the user asked for, or the one-line test they approved.

## Changing the code

- No dependencies, no build step. Keep it that way.
- UI strings live in the `T` table in `index.html`; add every key to `ko`, `en` and `zh`.
- Figures: edit `TEXT` in `docs/tools/make_figures.py`, run `python docs/tools/make_figures.py`, commit the SVGs.
- READMEs: `README.md` (English), `README.ko.md`, `README.zh-CN.md`. Change all three together.
