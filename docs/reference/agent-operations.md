# Agent operations

Agent-only reference (English). Read the relevant section when setting up or operating the app. [Index](README.md) · [Required rules](../../AGENTS.md).

## Setup procedure

Do these in order. Each step has a check; stop and tell the user when a check fails.

1. **Python 3.8+.** `python --version` (Windows may need `py -3 --version`).
2. **Reason Network is installed and signed in.**
   - `reason network who --all --json` exits 0 and prints JSON with a `sessions` array.
   - The database exists: `~/.reason/network/network.db`.
   - If either fails, the user must install Reason Network from <https://reasonmachines.com/network> and run `reason network`
     to sign in. Do not install it or sign in for them: it opens a browser sign-in.
   - On Windows the CLI is usually `%LOCALAPPDATA%\Reason\bin\reason.exe`, which `server.py` finds without PATH.
3. **Get the code.** Clone into a folder the user agrees to (default: `~/Reason-Network-Chat`).
   `git clone https://github.com/ehojune/Reason-Network-Chat`
4. **Start the server** as a background process from the repo folder: `python server.py`.
   It prints `Reason Network Chat on http://127.0.0.1:8765`. It exits with a clear message if the database is missing.
5. **Verify.** `GET http://127.0.0.1:8765/api/state` returns JSON whose `sessions` is non-empty and `whoError` is `null`.
6. **Open the page.**
   - Claude desktop app (Code tab): if the session's working folder is the repo, use the bundled `.claude/launch.json`
     (`preview_start` with name `reason-network-chat`). Otherwise add this entry to the working folder's `.claude/launch.json`,
     with the absolute path to `server.py`:

     ```json
     { "name": "reason-network-chat", "runtimeExecutable": "python",
       "runtimeArgs": ["-X", "utf8", "/absolute/path/to/Reason-Network-Chat/server.py"], "port": 8765 }
     ```

   - Anything else: open <http://127.0.0.1:8765> in a browser.
7. **Tell the user** the URL, how to stop the server, and the applicable limits from the [user manual](../manual.md#recovery).

Optional round-trip test, only with the user's OK (it starts a headless agent that takes work):
`python rnc.py worker start chat-codex --folder <a scratch folder> --agent codex`, send it a one-line message from
the page, confirm the reply appears, then `python rnc.py worker stop chat-codex`.

## Starting and restarting workers (agents read this)

Use `rnc.py`; never run `reason network serve` yourself.

```
python rnc.py worker list
python rnc.py worker start NAME --folder ABS_DIR --agent codex|claude [--model M] [--effort E] [--full-access]
python rnc.py worker start NAME          # a recorded worker, with its last settings
python rnc.py worker restart NAME        # running: Ctrl+C, end what was left under it, start again with its settings
python rnc.py worker stop NAME
python rnc.py worker adopt NAME [--model M] [--effort E]   # manage one started elsewhere (settings for restarts)
```

It talks to the running server (it reads the page token from `/`), or, with no server on `REASON_CHAT_PORT`, runs
the same `launcher.py` code itself over `REASON_CHAT_HOME`. Exit 0 on success, 1 on a refusal (printed), 2 on bad
usage. Why not `serve` directly:

- **Never start a worker inside your own turn.** A process started from your shell tool inherits the turn's output
  handles, so your turn cannot end until it exits, and the new worker's turns wait on yours. On 2026-10-24 a Codex
  lead started three workers in its own `codex exec` turn: that exec never finished, and every message to the lead
  for 45 minutes was taken and never answered. Through the server the worker starts outside your process tree;
  without a server, through the launcher's short-lived spawner with only a log file and no inherited handles.
- **PATH.** `serve` finds `codex` and `claude` on PATH. A `codex.cmd` first (npm installs one) makes every Codex turn
  fail with "contains a cmd.exe special character". The launcher puts the model shim and the real CLI first.
- **Environment.** The launcher removes your session's markers (`CODEX_THREAD_ID`, `CLAUDECODE`, …) and adds the
  stored user environment (`NODE_EXTRA_CA_CERTS` on a TLS-inspecting network).
- **Managed.** A worker started this way is recorded (`spawned.jsonl`, `worker-records.json`), so the page can
  change, restart and stop it; one you start yourself shows as *started elsewhere* until someone adopts it.

## Codex Fast mode

Codex launch/configure requests accept `fast: true|false|null`: Fast / Standard / inherit CLI config. Omitted speed
on configure preserves the worker's current choice; old records inherit. Codex live settings update the next
invocation without interrupting a turn. Restart records retain speed. Terminal windows receive the same overrides.
Other agent families reject explicit speed. CLI new Codex workers accept `--fast` or `--standard`.

## Gemini reviewer setup

`python rnc.py worker start gemini-reviewer --folder ABS_REPO --agent antigravity --model gemini-3.8-flash --effort medium`
starts a native `reason-network listen` receiver; it resumes Antigravity conversation IDs from
`REASON_CHAT_HOME/antigravity-workers/NAME/journal.sqlite3`. Keep that directory for restarts. Windows launches use
WMI and file logs, so no turn handles are inherited. Full access is refused. Invite its address into a room;
`@gemini-reviewer PR #N` (folder origin) or a full PR URL triggers a diff review, ordinary messages stay chat.
GitHub PR-open/mention webhooks are not implemented. P0 critical, P1 high, P2 normal, P3 minor.

Publishing requires the user's `~/bin/gh` agent shim and `gh-agent-token.py`, plus
`~/.config/gh-agents/gemini.{app,pem,identity}`. The helper must mint a Gemini App token; failure never falls back
to personal/Codex credentials. Reviews are COMMENT events on the inspected head with Gemini's model footer.
Check the returned API author against `GHA_LOGIN` and recheck the head before posting. Never copy tokens into
model input. A failed/uncertain call pauses new model work; `/status` reports it and `/retry` explicitly retries
retained requests. Successful cached results and posted-review markers prevent duplicate model calls/reviews.

## Starting a message in a group room (agents read this)

A member normally only answers what the room relays to it. To start a message yourself (a report when it is due,
a question for another member), run inside your own turn:

```
python rnc.py room list
python rnc.py room send ROOM --as YOUR_NAME "@member message"
# e.g. a lead's scheduled report:
python rnc.py room send dev-room --as lead-claude "@lead-codex 05:03 report: #898 merged, two lanes idle."
```

`ROOM` is a room id or name, `YOUR_NAME` your own session's name (the room envelope prints the exact command). It
goes out like your answer would: only to the members you @mention (an `@all` is not honoured: only the person
messages everyone), with the room envelope and their missed lines, within the room's limits, and answers to it
come back to you. It needs the server (exit 1 with the reason otherwise).

Who may post as whom: the server finds the process at the other end of the connection and walks its parents; the
post is taken when that member's own `serve` worker on this computer is among them (`via: "session"`). Anything
else is refused unless the user ticked the member under *May post first without proof* in the room's settings
(`via: "allowed"`, and the page says so on the post). Environment variables prove nothing (`serve` removes
`REASON_NETWORK_SESSION` from its agents, and any process can set one), so do not add an env-based shortcut.
