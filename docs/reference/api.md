# Configuration and HTTP API

Agent-only reference (English). Look up fields when changing a request or integration. [Index](README.md) · [Required rules](../../AGENTS.md).

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
  (`name, family, model, effort, fast, cwd, fullAccess, liveSettings, adopted`; `liveSettings`: a model, effort or speed change
  applies without a restart; `adopted`: taken back from a running process, model/effort may be `null` = unknown).
  `foreignWorkers[]` = `serve` workers running on this computer that this page did not start (no start proof).
  `workerRecords[]` = `{name, family, cwd, model, effort, fast, fullAccess, started}` of every worker started here, also
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
- `POST /api/launch` `{folder, agent, mode, model, effort, fast, name, fullAccess}` → `mode` is `worker` or `window`; empty
  `model`/`effort` mean the agent's own default; `name` is for workers (`[a-z0-9-]`, ≤ 48, not taken).
  `fullAccess` (bool, default false): a worker gets `serve --full-access`, a window the CLI's own flag
  (`launcher.FULL_ACCESS`); allowed only where the catalog's `modes.<mode>.fullAccess` is true.
  Every value is checked against the catalog; the folder must be an existing absolute local directory.
  Codex `fast`: `true` = Fast, `false` = Standard, `null` or omitted = inherit CLI settings. Other families reject
  explicit speed. See [Fast mode](agent-operations.md#codex-fast-mode).
  Returns `{ok, mode, name}`; 4xx with `{error}` otherwise.
- `POST /api/workers/configure` `{name, model, effort, fast, fullAccess, force}` → changes a worker this server started
  (404 otherwise); model and effort are checked against its family's catalog as for a launch. A Codex worker started
  with a settings file gets the new model/effort/speed written to `worker-settings/<name>.json` and uses it from its next
  `codex exec` (`{restarted: false}`). A permission change, any Claude change, or a worker from before settings files
  restarts it: Ctrl+C, a 1 s pause, `serve` again under the same name (`{restarted: true}`). The server asks `who`
  first; a busy worker that needs a restart answers 409 unless `force` is true. `{unchanged: true}` when nothing differs. While it
  restarts, its `workers.json` record stays until the new process replaces it, its name stays taken, it counts
  toward `MAX_WORKERS`, and configure or stop on it answers 409.
  Omitted `fast` preserves the existing speed; explicit `null` clears it to inherit. Live Codex settings changes
  apply to the next message without interrupting a running turn.
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
  Queued deliveries are persisted before sending and reconciled against the daemon database after interruption.
  With no receipt the outcome is unknown: the item stays queued until **Send all now** explicitly retries it once.
- `POST /api/prefs` `{key, value}` → saves one whitelisted setting: `hideOffline` (bool), `favorites` (up to 100
  session addresses or `room:<id>` keys, no repeats), `sideWidth` (int 180–900; the page also keeps it under 60 % of
  the window), `autoWake` (up to 50 session addresses the server wakes on unread messages). Returns `{ok, prefs}`.
  `collapsedSections` lists any of `favorites`, `rooms`, `now`, `later`, `offline`, `history`; omitted settings inherit
  the old `hideOffline` visibility until a section is changed.
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
