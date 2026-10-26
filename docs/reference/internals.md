# Implementation reference

Agent-only reference (English). Lookup material for code changes and diagnosis; not an onboarding checklist. [Index](README.md) · [Required rules](../../AGENTS.md).

## What it is

A local web page that shows Reason Network messages on this computer as a chat room, sends messages,
and starts new agent sessions.

| Part | Role |
|---|---|
| `server.py` | Python standard library HTTP server on `127.0.0.1:8765`. No dependencies. |
| `launcher.py` | New sessions: model catalogs, `reason network serve` workers, terminal windows, the model shims, permissions, changing a running worker. |
| `wake.py` | Wake a sleeping Codex session: `codex exec resume <thread> <fixed prompt>` in its folder; auto-wake with limits. |
| `prefs.py` | Viewer settings in `REASON_CHAT_HOME/prefs.json` (whitelisted keys), so they survive a lost localStorage. |
| `rooms.py` | Rooms: named sets of session addresses in `REASON_CHAT_HOME/rooms.json`. |
| `relay.py` | Group rooms: sends your message to the members it `@mentions` (or the room's default recipient) with their missed lines, passes on `@name` replies and returns a member's answer to the member who asked (one level), forwards a member's 1:1 answer into the room when you ask, queues hand-offs over the room's limits. |
| `rnc.py` | `python rnc.py worker` `list`, `start`, `restart`, `stop`, `adopt`: the supported way for an agent (or a script) to manage workers. |
| `index.html` | The whole UI (one file, no build). Polls `/api/state` every 3 s. Strings in ko/en/zh. |
| `tests/` | `python -m unittest discover tests` — request validation and catalog parsing, no agent needed. |
| `.claude/launch.json` | Lets the Claude desktop app start the server and show the page in its Browser pane. |
| `docs/tools/make_figures.py` | Regenerates every README figure. Never hand-edit the SVGs. |

## Data source

Read-only SQLite (`mode=ro` URI). Checked against Reason Network 0.12.10.

| Table | Columns used |
|---|---|
| `messages` | `id, sender, sender_agent, recipient, reply_to, body, wake, sent_at, read_at, held` |
| `sessions` | `name, agent, cwd, doing, tier` (only for sessions no longer in `who`) |

Live status (`busy`/`idle`/`offline`) is not in the database; it comes from `who --all --json`.
The page turns `tier` + status into plain words (`reach()` in `index.html`); under an unread `--fyi` message
(`wake = 0`) to a session that would get it at once it says *sent without waking* instead, since nothing pushes it. Measured here: idle Claude Code
sessions (`push`) read at once; Codex app sessions do not wake on a message (`push` idle: next turn; `pull`: only
when they check); `serve` workers (`worker: true`) answer at once. Re-measure before changing those labels.
If a Reason update changes the schema, `/api/state` returns HTTP 500 with the SQLite error; adjust the two queries in `state()`.

## Pitfalls

- **Never write the database** or open it without `mode=ro`. The daemon owns it.
- **One server per port.** On Windows `SO_REUSEADDR` (set by `HTTPServer`) lets a second server bind a port in use,
  and one of them then silently gets every request: on 2026-10-23 a stray preview from a working tree served the
  viewer for hours while the real server got nothing. `server.ChatServer` binds with `SO_EXCLUSIVEADDRUSE` on
  Windows, so a second start exits with "Port … is in use". Keep it; stop the old server before starting a new one.
- **Keep the bind address `127.0.0.1`.** The page shows private message text and can send as the user.
- **Message text is untrusted.** Bubbles render Markdown with `md()` in `index.html`: the text is HTML-escaped
  first, then only a fixed set of patterns become tags (tables, emphasis, code, lists, headings, quotes, rules,
  http(s) links with `rel="noopener noreferrer"`). Never insert message text as HTML any other way, and keep link
  targets to http(s) and ending at a quote. Any agent on the network can put text in front of the user here.
- **Do not parse CLI text output.** On Korean/Chinese Windows the console code page (CP949, GBK) garbles it. Use `--json` or the database. Decode subprocess output as UTF-8.
- **Windows batch shims.** If `REASON_BIN` points at a `.cmd`/`.bat`, cmd.exe would re-parse message text (`&`, `|`, `%`). `server.py` refuses to start; point it at `reason.exe`.
- **Idle Codex app sessions** leave a message unread until their next turn: nothing outside the Codex app can start one.
  Not a Reason Network Chat bug. The page marks non-worker, non-Claude sessions *reads next turn* and offers a worker
  in the same folder (`openLaunch({folder, agent})`). Workers from `reason network serve` answer at once.
- **`reason network serve codex` on Windows** can fail with "contains a cmd.exe special character" when a `codex.cmd` shim comes first on PATH. Start workers with `rnc.py` (or the page), which puts the shim and the real `codex.exe` first.
- **A stuck worker.** `serve` keeps a worker busy while a turn runs; a turn that hangs (an agent process waiting on a
  child that holds its handles) keeps it busy forever, and messages to it are read and queued, never answered. The
  page marks a worker busy for `REASON_CHAT_STUCK_MIN` with no new step (`doing` from `who`) and no new log line,
  and its right-click menu shows the process tree with a restart. A restart re-runs what was not answered: Reason
  keeps those requests in `~/.reason/ask-workers/<name>.json` and replays them when a worker of that name starts (the
  dialog lists them). If one of them caused the hang it can hang again. Do not edit that file; it is Reason's.
- **Replies to `<person>/terminal`** stay unread in the database because nothing else reads that inbox. The page hides the read mark for them.
- **Sending is acting for the user.** Send only what the user asked for, or the one-line test they approved.
- **Group rooms cost turns.** Each message wakes the members it names, and `@name` replies wake more. The limits in
  `relay.py` (`MAX_HOPS` 100, `BUDGET` 300 per `BUDGET_WINDOW` 600 s, or a room's own) are what stands between two
  agents and an endless exchange; keep a default limit. Over a limit a hand-off is queued, never dropped: users rely
  on the flow continuing. Only replies whose `reply_to` is a relayed message are passed on.
  Queued hand-offs are checked again before each send: one whose sender or recipient left the room is dropped,
  and the room's current hop limit decides whether it is held.
- **A member's answer goes back to the member who asked.** `Relay.answer_targets`: the members the answer
  `@mentions`, plus `sent[reply_to].speaker` when that speaker is a member (never the user, who sees the room anyway).
  One level only: a relayed message stored with `implicit: true` (an answer passed back this way) sends its reply to
  `@mentions` only. Drop that check and two agents thank each other until the budget runs out. `no_answer` sends
  nothing for text with no letter or digit (`-`, `—`) or a placeholder (`(해당 없음)`, `N/A`); do not add a length cut,
  because "4" or "no" are real answers (a 3-character cut dropped "4" in a live test). Answers passed back count
  toward the budget and hops like any hand-off. `compose` tells each agent where its answer goes; keep the envelope
  and `answer_targets` saying the same thing.
- **Statements and deliveries have separate identities.** `sent.source` is the original reply ID, preserved on
  resend/reconciliation. Room/all views attach delivery records to that statement; 1:1 views retain hand-offs.
  Legacy sources need a unique same-room match. `resolve_record` binds an envelope copy only to one exact
  sender/recipient/body family within 15 s of its canonical record; ambiguous matches stay unbound. Never replay
  an unbound envelope as new context. Markdown quotations/code and escaped mentions do not address members;
  keep Python `routing_text`, UI `routingText` and `tests/routing_cases.json` in sync.
- **The page's ↩ reply** puts one quoted line before the user's text with every `@` turned into `＠`, and works out
  recipients from the typed text only, so quoting a message never wakes the members it named. A reply belongs to its
  author: picking another recipient ends it, and cancelling removes the `@author` it added.
- **A 1:1 answer is not relayed.** `scan` passes on only replies to relayed messages, so a member answering the
  user's 1:1 message with `@mentions` reaches the user alone (on 2026-10-24 a lead's answer naming seven members went
  nowhere). Three things cover it: the page shows a 1:1 notice with the member's rooms above the message box;
  `/api/send` adds `relay.dm_note()` so the agent knows its mentions stay put (the page hides the note in the user's
  bubble, and `lines_for` cuts it from "Earlier in the room" lines at `DM_MARK`); and **Forward to room**
  (`Relay.forward`) passes such an answer on once, recorded in `forwarded` in `relay.json`. Keep `DM_MARK` the same
  in `relay.py` and `index.html`.
- **A worker's failure is not an answer.** When `serve` cannot run a turn it still replies (to the message, with
  `reply_to`): "The Codex worker failed: …" for a thrown error (a `codex.cmd` first on PATH gives "contains a cmd.exe
  special character"), "Codex failed: …" for a failed turn, "codex exited with N". `relay.FAILURE_RE` (the same in
  `index.html`) matches these, checked against Reason 0.12.10. Such a reply is passed on to nobody, never returned to
  an asker, dropped from the queue and from "Earlier in the room", and cannot be forwarded. On 2026-10-24 the answer
  return passed failures between workers whose own turns failed: 36 hand-offs in 34 s, bodies growing to 18 KB.
  The page shows a failure as a red notice and marks the message it answers *failed*; a message a `tier: "turn"`
  session read without answering for `NOANS_MS` (10 min) while not busy is *taken without an answer*. Both offer
  **Send again** (`/api/resend`) only while the recipient runs, and a bar per view lists them.
  `log_only_reply` also rejects responses consisting entirely of the Codex stdin preamble and timestamped
  `codex_*` diagnostic lines. The UI keeps their escaped original in collapsed details, including old relays.
  Quoted logs, user questions and logs accompanied by an actual answer remain ordinary messages. Shared
  `tests/worker_reply_cases.json` fixtures keep the Python and JavaScript classifiers aligned.
- **Relay state survives restarts.** `relay.json` keeps `sent` (relayed messages), `seen`, the scan cursor `since`,
  `done` (hand-offs already queued), `queue`, `forwarded` and `settled`. A restarted server resumes from `since` (at most `RESUME_MS`, 24 h,
  back), so replies that arrived while it was down are passed on once. Saves read the file and merge `sent` / `seen`
  first. Do not reset `since` to the start time: every live refresh restarts the server.
- **Agents may also use their own Reason tools.** A Codex or Claude member with the Reason Network MCP server can
  message another member directly instead of writing `@name`. The envelope asks them not to; those messages do not
  show in the room because they come from the agent's inner session (`codex exec` registers its own name).
- **Waking writes into the user's conversation.** `codex exec resume` appends a turn to that thread's rollout file.
  The page confirms each wake, and auto-wake only with the user's toggle (with its own confirmation). Test on a
  throwaway thread (start one with `codex exec` in a scratch folder), never on the user's conversations without their
  OK. `sessions.key` prefixes seen: `codex:<uuid>`, `claude-code:<id>`, `proc:<pid>` (Antigravity), `cli:<name>`
  (asks and workers); only `codex:` is woken.
- **The Codex app locks conversations.** Every thread the app (or a Codex TUI, or a running exec) has loaded keeps
  `CODEX_HOME/thread-writer-locks/<thread>.lock` locked until that process exits, even after `thread/unsubscribe`;
  `codex exec resume` then fails with "already has an active writer". `wake.held()` checks the lock by taking it for
  an instant (LockFileEx via `msvcrt.locking` on Windows, `flock` elsewhere). Measured with `codex app-server`
  (the desktop app's own binary, 0.163 alpha). Writing the app's automations from outside is unsupported; do not.
- **Auto-wake costs turns.** A Claude Code (push) session answers at once, so a Codex session on auto-wake and a
  Claude session can keep answering each other. The auto-wake limits in `wake.py` are what stops that; keep them.
- **Starting sessions is too.** A worker takes work on the network as the user and keeps running after the page
  closes. Start one only when the user asks, and stop test workers afterwards.
- **A killed worker looks alive.** `serve` reports "stopped" only when it exits on Ctrl+C. After `taskkill /F`
  (or a crash) the network keeps showing it idle, and its name stays taken. `/api/stop` sends Ctrl+C to the
  worker's own hidden console; to clear a stale entry, start a worker with the same name and stop it there.
- **Agent-session variables.** A server started from inside an agent (the Claude desktop preview, a Codex shell)
  inherits that session's markers (`CLAUDECODE`, `CODEX_THREAD_ID`, `CODEX_SANDBOX*`, and `CLAUDE_CODE_*` when inside
  Claude Code). `launcher.base_env()` removes them for children, or a new agent thinks it is nested. Credentials and
  settings (`CODEX_API_KEY`, `CODEX_HOME`, …) and anything in the stored user environment are kept.
<a id="workers-and-models"></a>

- **Workers and models.** `reason network serve` (checked in 0.12.10) has no model or effort flag. `serve codex`
  runs `codex exec --json --skip-git-repo-check (--sandbox workspace-write | --dangerously-bypass-approvals-and-sandbox)`
  per message; `serve claude` keeps a warm `claude -p --input-format stream-json … --permission-mode (acceptEdits |
  bypassPermissions)` per sender plus a spare, both found through PATH. So every worker's PATH starts with
  `codex-shim/` or `claude-shim/`, whose `codex`/`claude` adds `model_args()` and runs the real CLI
  (`REASON_CHAT_SHIM_REAL`). The arguments come from `REASON_CHAT_SHIM_SETTINGS` (the worker's file, read on every
  run), else `REASON_CHAT_SHIM_ARGS`; the old `REASON_CHAT_CODEX_REAL`/`_ARGS` names still work for workers started
  before, and new workers get them too, because a running turn can hold the old shim `.exe` open so it is not
  replaced yet. A worker gets a settings file only when the shim on disk is this version (`shim_current()`);
  otherwise a later change restarts it. An effort in `CLAUDE_CODE_EFFORT_LEVEL` does not reach a `claude -p` stream-json child; do not go back to
  it. On Windows the shim is an `.exe` built from pip's script launcher (Bun refuses message text for `.cmd`);
  without pip, workers use the agent's default model and the page says so.
- **Full access is dangerous by design.** A full-access worker runs whatever a network message (or a group-room
  relay) asks, without approval. The page confirms it each time it is chosen; keep that confirmation.
- **Lost workers are taken back.** `workers.json` can lose entries (two servers writing it from memory did). Every
  30 s `launcher.discover()` lists processes (PowerShell `Win32_Process` on Windows, `ps` elsewhere), parses
  `reason network serve [claude|codex] --name N --cwd D [--full-access]`, and re-registers a worker whose pid and
  creation time are in `spawned.jsonl` (appended at every start, so it survives a `workers.json` that lost the
  worker), or that has written `logs/N.log` since its process started (started with the page's recipe, e.g. by a
  script). A log last written before the process started is an older worker's and proves nothing. Model and effort come from the agent processes under it
  when one runs. Others are only listed (`foreignWorkers`) until the user adopts one. An adopted outside worker is
  never stopped with the console-wide Ctrl+C (it may share the user's console): POSIX gets SIGINT to its pid, Windows
  a forced tree kill. A worker with no known folder is not restarted. Linux argv comes from `/proc` (`ps` loses
  argument boundaries); macOS uses `ps` for parent pids and `KERN_PROCARGS2` for argument boundaries, with `lsof`
  for the client socket owner. Where processes cannot be read nothing is taken back and no
  name is treated as free (fail closed). PowerShell output is forced to UTF-8. Saves read `workers.json` and
  keep live records another writer added, except names stopped here.
- **Workers and windows outlive the server.** The Claude desktop app stops a preview by killing its process tree,
  so `launcher.spawn()` starts them through a short-lived spawner and they are never the server's descendants.
  `workers.json` keeps pid + creation time, so a restarted server still recognises and stops its workers.
- **Terminal windows** (Windows only) open with `CREATE_NEW_CONSOLE`. They join the network when the agent's
  session starts; Codex starts it with the first prompt.

## Model catalog sources

| Agent | Models from | Efforts from |
|---|---|---|
| Codex | `~/.codex/models_cache.json` | the levels that model supports |
| Claude Code | aliases in `claude --help`, plus extra models in `~/.claude.json` | `--effort` in `claude --help` |
| Antigravity | `agy models` | the model ids' endings (`-low`, `-high`, …) |
