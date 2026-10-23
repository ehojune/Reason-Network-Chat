# AGENTS.md — setting up and operating Reason Network Chat

For coding agents. Your user pasted this repo's URL and asked you to set it up, or is working in this repo.
The README is for the human; this file has the procedure, checks, configuration and pitfalls.

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
7. **Tell the user** the URL, how to stop the server, and the "Good to know" points from the README that apply.

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

## Configuration

| Variable | Default | Use |
|---|---|---|
| `REASON_CHAT_PORT` | `8765` | Listening port. Also change `port` in `launch.json`. |
| `REASON_CHAT_DB` | `~/.reason/network/network.db` | Daemon database path. |
| `REASON_BIN` | `%LOCALAPPDATA%\Reason\bin\reason.exe` on Windows, else `reason` on PATH | The Reason CLI. |
| `NODE_EXTRA_CA_CERTS` | unset | Root CA file for TLS-inspecting corporate networks. The CLI (Bun) needs it there. On Windows, children get it from the stored user environment even if the server started before it was set. |
| `REASON_CHAT_HOME` | `~/.reason-network-chat` | Rooms (`rooms.json`), relayed-message records (`relay.json`), settings (`prefs.json`), running wakes (`wakes.json`), auto-wake limits (`autowake.json`), worker registry (`workers.json`), last settings of every worker started here (`worker-records.json`, kept after the process dies), start proofs (`spawned.jsonl`), worker logs (`logs/`), the model shims (`codex-shim/`, `claude-shim/`) and each worker's shim arguments (`worker-settings/<name>.json`). |
| `REASON_CHAT_CLAUDE`, `REASON_CHAT_CODEX`, `REASON_CHAT_AGY` | found automatically | Full path to an agent CLI. On Windows it must be an `.exe`. |
| `REASON_CHAT_STUCK_MIN` | `30` | Minutes a worker may be busy with no new step and no new log line before it shows as possibly stuck. |
| `REASON_CHAT_MAX_HOPS`, `REASON_CHAT_BUDGET`, `REASON_CHAT_BUDGET_WINDOW` | `100`, `300`, `600` | Default group-room limits: hops in one hand-off chain, hand-offs per window (seconds). A room's own setting wins. |

## HTTP API

Every endpoint accepts only `Host: 127.0.0.1:<port>` or `localhost:<port>` (DNS-rebinding guard).
Every POST also needs `Origin: http://127.0.0.1:<port>` (or `localhost`), `Content-Type: application/json`, and
`X-Reason-Chat-Token` equal to the token in the page's `<meta name="reason-chat-token">` (new each server start).
Responses forbid framing. To act from a script, use the `reason` CLI instead.
`/api/state` carries `api` (`API` in `server.py`). Bump it together with `API` in `index.html` whenever a field or
endpoint changes shape: the page reads `index.html` fresh from disk, so a server started before an update meets a
newer page; on a mismatch the page asks for a restart instead of failing. `boot` (random per server start, also
written into the page) tells an open page that the server restarted: it reloads itself (at most once a minute) to
get the new token, and a newer server also triggers a reload.

- `GET /api/state` →
  `{api, boot, team, me, sessions[], messages[], launched[], rooms[], relays{}, queued{}, notices{}, forwarded{}, settled{}, relayDefaults{}, prefs{}, wakes{}, whoError, now}`.
  Each session also has `resumable` (a Codex session of yours on this computer) and `appOpen` (another Codex process,
  usually the desktop app, holds the thread's writer lock, so it cannot be woken); `wakes{}` = address →
  `{status: running|done|failed, at, error, auto, limitUntil?}` (`limitUntil`: auto-wake rests until then).
  `me` is the address the page sends as (`<person>/terminal`).
  `sessions[]` = live entries from `who --all --json` (`address, name, agent, status, doing, cwd, tier, live: true`)
  plus addresses seen only in history (`status: "gone"`, `live: false`).
  `messages[]` = rows of the `messages` table ordered by `sent_at` (ms epoch).
  `launched[]` = workers this server started and that are still running
  (`name, family, model, effort, cwd, fullAccess, liveSettings, adopted`; `liveSettings`: a model or effort change
  applies without a restart; `adopted`: taken back from a running process, model/effort may be `null` = unknown).
  `foreignWorkers[]` = `serve` workers running on this computer that this page did not start (no start proof).
  `workerRecords[]` = `{name, family, cwd, model, effort, fullAccess, started}` of every worker started here, also
  dead ones. A session of a recorded worker keeps `agent` = codex / claude-code (the database stores serve workers as
  `cli`) and gets `worker: true`; `inner` names the worker when the session is that worker's own agent session
  (`<worker>-claude[-N]`, its warm `claude -p` registering itself), which the page folds away. `stale: true` marks a
  recorded worker that `who` shows busy/idle here although no serve process with its name runs (killed mid-turn);
  the page shows it as stopped (only the network's entry is left). Known after the first 30 s discovery pass.
  A busy worker of this computer (`tier: "turn"`) also gets `quietSince` (ms: its last step change, seen by the
  `who` poll, or log line, whichever is later) and `stuck: true` once that is `STUCK_MS` ago.
  `rooms[]` = `{id, name, members[], group, created, limits, defaultTo, allowPost}`; `members` are session addresses; `limits` =
  `{hops?, budget?}` (a number, or `null` for no limit; a missing key means the default); `defaultTo` = the member
  an unmentioned message goes to, or `null`; `allowPost` = members whose `rnc.py room send` is taken without proof.
  `relays{}` = for messages this page relayed into a group room: `{room, hop, core, speaker, post}` (`post`:
  `"session"` or `"allowed"` when the member started the message with `rnc.py room send`; `core` is the plain
  message without the room envelope; `hop` 0 = yours, ≥1 = a member's reply passed on). `queued{}` = room →
  `{waiting, held}`: hand-offs over the budget waiting to go out in order, and those held past the hop limit.
  `relayDefaults` = `{hops, budget, window}` from the environment.
  `notices{}` = room → the last hand-off that still failed after 3 tries.
  `forwarded{}` = message id → `{room, to[]}` for 1:1 answers you forwarded into a group room.
  `settled{}` = message id → `{how: resent|dismissed, at}` for your messages sent again or put aside.
- `POST /api/send` `{to, body, fyi}` → runs `reason network send <to> <body> [--fyi]`. When `to` is a member of a
  group room, `relay.dm_note()` is added to the body (also for each member of a plain room).
  Returns `{ok, rc, out, err}`; HTTP 502 when the CLI fails.
- `GET /api/catalog[?refresh=1]` → `{families[], folders[]}`. Each family: `id` (`claude`/`codex`/`antigravity`),
  `installed`, `models[]` (`id, label, efforts[], defaultEffort`), `defaultModel`, `defaultEffort`, `note`, and
  `modes.worker` / `modes.window` (`ok, why, models, modelsWhy, fullAccess`). Cached 10 minutes.
- `POST /api/launch` `{folder, agent, mode, model, effort, name, fullAccess}` → `mode` is `worker` or `window`; empty
  `model`/`effort` mean the agent's own default; `name` is for workers (`[a-z0-9-]`, ≤ 48, not taken).
  `fullAccess` (bool, default false): a worker gets `serve --full-access`, a window the CLI's own flag
  (`launcher.FULL_ACCESS`); allowed only where the catalog's `modes.<mode>.fullAccess` is true.
  Every value is checked against the catalog; the folder must be an existing absolute local directory.
  Returns `{ok, mode, name}`; 4xx with `{error}` otherwise.
- `POST /api/workers/configure` `{name, model, effort, fullAccess, force}` → changes a worker this server started
  (404 otherwise); model and effort are checked against its family's catalog as for a launch. A Codex worker started
  with a settings file gets the new model/effort written to `worker-settings/<name>.json` and uses it from its next
  `codex exec` (`{restarted: false}`). A permission change, any Claude change, or a worker from before settings files
  restarts it: Ctrl+C, a 1 s pause, `serve` again under the same name (`{restarted: true}`). The server asks `who`
  first; a busy worker answers 409 unless `force` is true. `{unchanged: true}` when nothing differs. While it
  restarts, its `workers.json` record stays until the new process replaces it, its name stays taken, it counts
  toward `MAX_WORKERS`, and configure or stop on it answers 409.
- `POST /api/workers/adopt` `{name, model?, effort?}` → manage a worker from `foreignWorkers[]` here (the user
  confirms it in the page, or `rnc.py worker adopt`). `model`/`effort`: what it is known to run with (checked against
  the catalog), kept for restarts; the process is not touched. Returns `{ok}`; 404 when no such worker runs.
- `POST /api/workers/reboot` `{name}` → a running worker managed here: `Launcher.relaunch` (Ctrl+C, or a forced tree
  kill for an adopted one; then every process that was under it, such as a hung agent turn; then `serve` again with
  its recorded settings). A stopped recorded one is started as by `/api/workers/restart`. One started elsewhere: 409
  (adopt it first). Returns `{ok, restarted}`.
- `GET /api/workers/procs?name=N` → `{name, pid, managed, pending[], procs[{pid, ppid, name, cmd}]}`: a running
  worker's `serve` and its descendants (a pid older than its parent is a reused pid and left out), and `pending`,
  the messages it took but has not answered, read from Reason's `~/.reason/ask-workers/<name>.json`.
- `POST /api/workers/restart` `{names[]}` → starts recorded workers again with their last settings (checked against
  the catalog like a launch). Refused (409): a name whose `serve` runs on this computer (process list) or that is
  online on another computer of this person (`who`). A name `who` still shows here only because its process was
  killed is free: Reason accepts a new `serve` under it. `/api/launch` treats such a stale name of ours (a record or
  a log here) the same way. Returns `{ok: true, started, results[{name, ok, error?, code?}]}`.
- `POST /api/rooms/save` `{id?, name, members[], group, limits?, defaultTo?, allowPost?}` → creates a room (no `id`) or replaces
  its name, members, group flag, limits and default recipient. Members: 1–12 known session addresses, not the page's
  own. `limits`: `{hops?, budget?}`, each 1–100000 or `null` (no limit). `defaultTo`: one of the members, or `null`.
  Returns `{ok, room}`.
- `POST /api/rooms/delete` `{id}` → removes the room; messages are untouched.
- `POST /api/rooms/send` `{id, body, fyi}` → a plain room: one `reason network send` per member. A group room: only to
  the members the body `@mentions` (`@all`, `@everyone`, `@모두`, `@전체` = every member), else to `defaultTo`, else
  HTTP 400 (nothing is sent to everyone by default); each copy carries the room envelope; `fyi` is ignored. Returns
  `{ok, sent, results[{to, ok, err}]}`; `ok` when at least one member got it.
- `POST /api/rooms/post` `{id, as, body}` → a member starts a message in a group room (`rnc.py room send`): queued
  like its answer (`Relay.post_as`: hop 1, to the members it `@mentions`, never `@all`). Taken only when the caller
  runs inside that member's own worker here (`Launcher.caller_worker`: the connection's client pid, then its
  parents) or the member is in `allowPost`; else 403. `as`: the member's address, or a name only one member has.
  Returns `{ok, to[], via}`.
- `POST /api/rooms/forward` `{id, message}` → passes a member's message to you (an answer to a 1:1 message) on to
  the members of group room `id` it `@mentions`, as a hand-off with that member as speaker (hop 1, queued within the
  room's limits). Once per message (409 after that, or when it answers a relayed room message: the room passes those
  on itself); 400 when it mentions no other member or its sender is not a member. Returns `{ok, to[]}`.
- `POST /api/resend` `{ids[], dismiss}` → for each of your messages (1–100): send it again as it was (a relayed one
  through `Relay.redeliver`, same room, member, speaker and text; a 1:1 one with `reason network send`), or with
  `dismiss` put it aside. Once per message (`claim`, kept in `settled` in `relay.json`; a send that fails is
  released again). Refused per message when its recipient is offline. Returns `{ok, done, results[{id, ok, to?, err?}]}`.
- `POST /api/rooms/flush` `{id}` → marks every queued hand-off of the room to go out now, past its budget and hop
  limit ("Send all now"); the relay loop sends them within a few seconds. Returns `{ok, released}`.
- `POST /api/prefs` `{key, value}` → saves one whitelisted setting: `hideOffline` (bool), `favorites` (up to 100
  session addresses or `room:<id>` keys, no repeats), `sideWidth` (int 180–900; the page also keeps it under 60 % of
  the window), `autoWake` (up to 50 session addresses the server wakes on unread messages). Returns `{ok, prefs}`.
- `POST /api/wake` `{address}` → wakes a Codex session (`wake.py`): yours, on this computer, not busy, with unread
  messages, not open in the Codex app (HTTP 423 if it is). The thread id comes from `sessions.key` (`codex:<uuid>`),
  the folder from `sessions.cwd`, the prompt is `WAKE_PROMPT`; nothing from the request is run. Answers at once;
  progress shows in `wakes{}`. Auto-wake runs the same `wake()` from a server loop every 10 s for the `autoWake` list,
  limited by `AUTO_GAP` (60 s), `AUTO_BUDGET`/`AUTO_WINDOW` (12 per hour) and `AUTO_RETRY` (600 s after a failure),
  kept in `autowake.json` across restarts. Only an unread message with `wake = 1` and `held = 0` triggers it (not `--fyi`).
  The wake starts detached (like a worker, log in `logs/wake-<name>.log`) and is judged from the database: `done`
  when the messages unread at its start are read, else `failed` with the log's last lines. `wakes.json` lets a
  restarted server watch running wakes to the end and judge those that ended while it was down.
- `POST /api/stop` `{name}` → stops a worker this server started: Ctrl+C first (so the network shows it as stopped),
  then a kill after 10 s.

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
  argument boundaries); macOS has no discovery, and where processes cannot be read nothing is taken back and no
  name is treated as free (fail closed). PowerShell output is forced to UTF-8. Saves read `workers.json` and
  keep live records another writer added, except names stopped here.
- **Workers and windows outlive the server.** The Claude desktop app stops a preview by killing its process tree,
  so `launcher.spawn()` starts them through a short-lived spawner and they are never the server's descendants.
  `workers.json` keeps pid + creation time, so a restarted server still recognises and stops its workers.
- **Terminal windows** (Windows only) open with `CREATE_NEW_CONSOLE`. They join the network when the agent's
  session starts; Codex starts it with the first prompt.

## Changing the code

- No dependencies, no build step. Keep it that way. Run `python -m unittest discover tests` before a PR.
- Model and effort lists come from each agent's own catalog (`launcher.py`). Do not add a hard-coded model list.
- UI strings live in the `T` table in `index.html`; add every key to `ko`, `en` and `zh`.
- Figures: edit `TEXT` in `docs/tools/make_figures.py`, run `python docs/tools/make_figures.py`, commit the SVGs.
- Docs for people come in three languages: English `X.md`, Korean `X.ko.md`, Chinese `X.zh-CN.md`, each starting with
  the same language switcher row (English · 한국어 · 中文). Change all three together, and give any new doc the same set.
  `AGENTS.md` and `CLAUDE.md` are English only.
- Patch notes: every pull request adds one row at the top of `patch_notes/README.md`, `README.ko.md` and
  `README.zh-CN.md` (time in KST, PR link, one sentence on what changed for the user). New date → new `## YYYY-MM-DD` heading.
