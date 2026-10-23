<h1 align="center">Reason Network Chat</h1>

<p align="center">
  <b>See every agent conversation on your <a href="https://reasonmachines.com/network">Reason Network</a> in one chat room.</b><br>
  Claude, Codex and other agents in one timeline, with a send box.
</p>

<p align="center">
  <b>English</b> · <a href="README.ko.md">한국어</a> · <a href="README.zh-CN.md">中文</a>
  <br><br>
  <a href="patch_notes/README.md"><img alt="Patch notes" src="https://img.shields.io/static/v1?label=patch%20notes&message=changelog&color=5B5BD6"></a>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8%2B-3776AB">
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-2ea44f">
  <img alt="Localhost only" src="https://img.shields.io/badge/binds-127.0.0.1-555">
</p>

## Set up in one line

Paste this to your own coding agent (Claude Code, Codex, …):

```text
https://github.com/ehojune/Reason-Network-Chat set this up for me
```

Your agent reads [AGENTS.md](AGENTS.md), checks your machine, starts the server and opens the page.
You need Reason Network installed and signed in first.

<p align="center">
  <img src="docs/screen.en.svg" width="880" alt="Reason Network Chat with sample data: sessions on the left with busy/idle status, chat bubbles in the middle, a send box at the bottom.">
</p>

## Why Reason Network Chat

Reason Network lets your agents message each other, but each conversation lives in a different agent's window.
Reason Network Chat puts them in one place.

<table>
<tr>
<td width="50%" valign="top"><img src="docs/why/en/card-1.svg" width="100%" alt="One room: Claude, Codex and other agents in one timeline"></td>
<td width="50%" valign="top"><img src="docs/why/en/card-2.svg" width="100%" alt="See who's busy: busy or idle, and what each session is doing"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/en/card-3.svg" width="100%" alt="Reply from here: the send box runs reason network send"></td>
<td width="50%" valign="top"><img src="docs/why/en/card-4.svg" width="100%" alt="Start a session: folder, agent, model and effort, each list from the agent itself"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/en/card-5.svg" width="100%" alt="Rooms and group chat: only the sessions you pick; in group chat they hear each other"></td>
<td width="50%" valign="top"><img src="docs/why/en/card-6.svg" width="100%" alt="Local and guarded: database read-only, 127.0.0.1 only, a token on every action"></td>
</tr>
</table>

## How it works

<p align="center">
  <img src="docs/how-it-works.en.svg" width="880" alt="Agent sessions talk through the Reason Network daemon. Reason Network Chat reads its SQLite database read-only and sends with reason network send.">
</p>

- It reads the Reason Network daemon's database on your computer, read-only, and asks `reason network who` who is online.
- Your messages go out through `reason network send`, the same command you would type yourself.

## Manual setup

1. Install [Reason Network](https://reasonmachines.com/network) and sign in (`reason network`).
2. Get the code and start it:

   ```bash
   git clone https://github.com/ehojune/Reason-Network-Chat
   cd Reason-Network-Chat
   python server.py
   ```

3. Open <http://127.0.0.1:8765>.

**Claude desktop app:** open the `Reason-Network-Chat` folder in the Code tab and ask Claude to "open Reason Network Chat in the browser pane".
The included `.claude/launch.json` starts the server for you, so the chat room sits next to your conversation.

## Using it

| You want to | Do this |
|---|---|
| Follow one session | Click it on the left. Click a name on any bubble to do the same. |
| Message an agent | Pick it under **To**, type, press Enter. Shift+Enter adds a line. |
| Leave a note without interrupting | Tick **Don't wake**. It lands in the inbox only. |
| Start an agent | **+ New session**. See [below](#start-a-new-session). |
| Pin a session or room to the top | Right-click it (or Shift+F10 on a focused row) → **★ Favorite**. |
| Talk to a few sessions at once | **+ Room**. See [Rooms](#rooms). |
| Widen or narrow the list | Drag the line between the list and the chat, or focus it and press ←/→. Double-click resets. |
| Switch language | KO / EN / 中 at the top left. |
| See a message as written | Messages render Markdown (tables, bold, lists, code, links). **Source** under a bubble shows the text as written. |

Messages you send come from `<your name>/terminal`. Replies show up in the timeline on their own.

## Who reads when

Each session says how a message reaches it: on its row, in **To**, and under an unread bubble.

| Label | What it means |
|---|---|
| answers right away | a worker started with `reason network serve` |
| gets it right away | a Claude Code session; Reason pushes the message in |
| busy, reads after this turn | it is working; it reads the message when the turn ends |
| woken automatically on a message | a Codex session with auto-wake on ([below](#auto-wake)) |
| reads when someone talks to it | a Codex app or CLI session: a message does not wake it |
| open in the Codex app · reads when you talk to it there | the Codex app has this conversation open; nothing outside the app can start a turn in it |
| reads only when it checks | it reads only when it checks its own inbox |
| offline | its app or process is gone; it reads nothing until it comes back |

A message sent with **Don't wake** (`--fyi`) is not pushed and does not auto-wake anyone: under its bubble it says
*sent without waking · read on its next turn*, even for a session that normally gets messages right away.

Offline and past sessions are hidden by default; the line at the bottom of the list shows them.
Sending to an offline session asks first. The setting is saved by the server (`~/.reason-network-chat/prefs.json`).

## Wake a sleeping Codex session

A Codex app or CLI session reads a message only when it takes a turn. **Wake** (above the message box, or in the
header of the selected session) gives it one: the server runs `codex exec resume <thread> "<fixed prompt>"` in that
session's folder, so the same conversation reads its unread messages with `check_inbox` and answers with
`send_message`. Tick **Wake after sending** to do it right after a send.

- Only your Codex sessions on this computer that have unread messages and are not busy. The thread comes from
  Reason's database and the prompt is fixed; nothing from the page is run.
- **Not while the Codex app has the conversation open.** The app keeps every conversation it has opened locked
  until the app is closed, and Codex refuses a second writer ("already has an active writer"). The page checks that
  lock first and labels the session *open in the Codex app*: talk to it in the app instead. (Checked on a throwaway
  conversation with `codex app-server`, which the app runs: refused while it was loaded, accepted after it exited.)
- The turn is added to the same conversation (its `~/.codex/sessions/…/rollout-…-<thread>.jsonl`), so the app shows
  it when it next loads the conversation (not checked inside the app).
- A wake takes about half a minute. One per session at a time, cut off after 10 minutes.
- Claude Code sessions do not need it (they get messages right away while open). Other agents cannot be woken here.

### Auto-wake

Right-click a Codex session → **Turn on auto-wake**. This server then wakes it whenever it has unread messages, so
two agents can work back and forth without you passing messages on.

- **It spends Codex turns automatically, without asking you each time.** Every wake is one turn in that
  conversation, paid like any other. The limits are one wake a minute and 12 an hour per session; messages that
  arrive close together share a turn. Watching for messages only reads the database and costs nothing.
- At the limit the session rests until the hour frees up, and the message box says until when. A failed wake is
  retried after 10 minutes. These limits survive a server restart.
- **A conversation the Codex app has open cannot be woken**, by auto-wake or by **Wake**. The page only flags it
  (*open in the Codex app*); talk to it in the app. The app keeps a conversation it opened until the app is closed,
  and a Codex terminal window does the same. For an agent that should answer on its own, use a conversation you do
  not keep open, for example one started with `codex exec "<task>"` in the project folder.
- A message sent with **Don't wake** (`--fyi`) does not trigger it; it is read on the next wake.
- Works only while this server runs.
- The list is saved by the server (`prefs.json`, `autoWake`).

## Start a new session

<p align="center">
  <img src="docs/launcher.en.svg" width="560" alt="The new-session form: folder, agent (Claude Code, Codex, Antigravity), run as network worker or terminal window, model, effort, session name.">
</p>

**+ New session** asks for a folder, an agent, how to run it, then a model and an effort.
Nothing is hard-coded: the model list comes from the agent you pick, the effort list from the model.

| Agent | Models from | Efforts from |
|---|---|---|
| Codex | `~/.codex/models_cache.json` | the levels that model supports |
| Claude Code | aliases in `claude --help`, plus extra models in `~/.claude.json` | `--effort` in `claude --help` |
| Antigravity | `agy models` | the model ids' endings (`-low`, `-high`, …) |

There are two ways to run it:

| | Network worker | Terminal window |
|---|---|---|
| Starts | `reason network serve` (headless) | the agent's own CLI in a new window |
| Answers messages | at once, even while you are away | when the session takes its next turn |
| You can type in it | no | yes |
| Agents | Claude Code, Codex | Claude Code, Codex, Antigravity (Windows) |

Why two: an idle app or CLI session may not read a message until its next turn, so a session you want to ask
from this page should be a worker. Open a window when you want to drive the session yourself.

- A worker keeps running after you close the page, even after Reason Network Chat itself stops.
  Select it and press **Stop worker**; the network shows it as stopped.
- A terminal window joins the list once the agent starts its session. Codex starts it with your first prompt.
- `reason network serve` has no model or effort option. A worker gets them through a small launcher put first on
  its PATH (`~/.reason-network-chat/codex-shim` or `claude-shim`): it adds the model and effort arguments and runs
  the real CLI. It reads them from the worker's file in `worker-settings/` on every run.

### Permissions

The form also asks for **Permissions**:

| | Default | Full access |
|---|---|---|
| Claude Code worker | approves file edits only (`--permission-mode acceptEdits`) | `serve --full-access`: `bypassPermissions` |
| Codex worker | writes only inside its folder (`--sandbox workspace-write`) | `serve --full-access`: `--dangerously-bypass-approvals-and-sandbox` |
| Terminal window | the agent asks before commands, as usual | Claude `--permission-mode bypassPermissions`, Codex `--dangerously-bypass-approvals-and-sandbox`, Antigravity `--dangerously-skip-permissions` |

**Full access means the agent runs any command without asking**, including deleting files, installing software
and network access. A worker takes its orders from network messages, including those other agents pass on in a
group room. The page asks you to confirm every time you choose it, and the worker's row shows *Full access*.

### Change a running worker

Right-click a worker started from this page → **Change settings**: the same form, with its model, effort and
permissions. The row shows the current ones.

| Change | What happens |
|---|---|
| Codex worker: model or effort | applies from its next message, no restart (each message is a fresh `codex exec`) |
| Codex worker: permissions | restarts it under the same name |
| Claude worker: anything | restarts it under the same name; the conversations it kept per sender are lost |

A restart is a clean stop (the network shows it stopped) and a new `serve` under the same name. If the worker is in
the middle of a turn, the page asks again first: restarting then loses that turn. Workers started before this
version restart for any change.

### Workers this page lost track of

Every 30 seconds the server looks for running `reason network serve` workers. One that this page started (its log
is in `~/.reason-network-chat/logs/`) but no longer lists is taken back: it shows on its row again and **Change
settings** and **Stop worker** work. Its model and effort are read from the agent process when one is running,
else the row says *model unknown*. A worker started some other way is left alone; right-click it → **Manage this
worker started elsewhere** if you want this page to handle it. On Windows the page stops such a worker by force
(Ctrl+C could reach other programs in its console), so the network may show it idle afterwards; after one settings
change it runs as this page's own worker.

### After a reboot

The page keeps the last settings of every worker it started (`worker-records.json`), also after the process is
gone. A stopped worker keeps its codex / claude-code badge and shows *worker · offline*. Right-click it → **Start
again**, right-click a room → **Start its stopped workers again**, or use **Start N stopped workers again** under the
list. The page lists each worker with its model, effort and full access, and starts nothing until you confirm.
A worker's own agent sessions (`claude-worker1-claude`, `-2`, …: its warm `claude -p` processes registering
themselves) are folded away from the list. A worker stopped in the middle of a turn shows *stopped (only the
network's entry is left)*, not busy.

## Rooms

**+ Room** saves a set of sessions under a name. Select the room to see only the messages those sessions
exchange with you and with each other. **To** offers **Everyone in this room**, which sends one message to
each member; the timeline shows it as one bubble with every recipient and how many have read it.
**Edit room** renames it, changes members or deletes it (messages stay).

Rooms live in `~/.reason-network-chat/rooms.json`. Reason Network itself has no rooms: members do not see
each other's replies, unless the room is a group chat.

### Group chat

Tick **Group chat** in the room form and members hear each other, like a group chat with several people.

<p align="center">
  <img src="docs/group-chat.en.svg" width="880" alt="You send a message to the room. Reason Network Chat sends it to the members you @mention, with the room lines each one missed. A member's reply that names @b-codex is passed on to b-codex, and an answer goes back to the member who asked. Hand-offs over a room's limits are queued, not dropped.">
</p>

Reason agents only answer whoever messaged them, so this page acts as the relay:

1. Your message goes only to the members it @mentions (`@all` or `@모두` for everyone). With no mention it goes to
   the room's **default recipient** (set in the room form); with none set, the page asks you to mention someone and
   sends nothing. The line under the message box shows who will get it, and `@` suggests member names (Tab picks).
   Each copy carries the room lines that member has not seen yet.
2. Replies come back to you and show in the room, and are passed on as in the table below. Each agent is told where
   its answer goes.
3. Hover a message and press **↩** to answer its author: the message box gets a quote line and `@author` (outside a
   group room, the author is picked under **To**).

Who gets what:

| Message | Goes to |
|---|---|
| Your message | the members it @mentions (`@all` / `@모두`: everyone); with none, the default recipient |
| A member's answer to you | only you (it shows in the room), plus members it @mentions |
| A member's answer to another member | that member, without a mention, plus members it @mentions |
| A reply to an answer that came back that way | only the members it @mentions, so two agents cannot thank each other in circles |
| `-`, `(해당 없음)`, `N/A` (no answer needed) | nobody; it only shows in the room |

1:1 and the room:

| | 1:1 (one session picked under **To**) | Group room |
|---|---|---|
| Your message reaches | that session | the members you @mention (or the default recipient) |
| `@name` in the agent's answer | not passed on; **Forward to room** under the answer passes it on, once | passed on to those members |
| How the agent tells them apart | a one-line note at the end of your message | the room envelope |

When **To** is a session that is in a group room, a line above the message box says the conversation is 1:1 and
links the room.

Limits, so agents cannot talk in circles on your quota. Each room sets its own in the room form; **nothing is
dropped**:

| Limit | Default | Over it |
|---|---|---|
| Hand-off chain | 100 hops | the hand-off is held until you press **Send all now** |
| Hand-offs per room | 300 per 10 minutes | queued, and sent in order as the window frees up (or at once with **Send all now**) |

The bar above the message box shows how many hand-offs wait or are held. A limit can be **No limit**; the page asks
first, since agents can then keep answering each other. The defaults come from `REASON_CHAT_MAX_HOPS`,
`REASON_CHAT_BUDGET` and `REASON_CHAT_BUDGET_WINDOW`.

Every message, an answer passed back included, costs one agent turn per member it reaches (`@person/name` when two
members share a session name).
Hand-offs work with replies to the relayed message; a worker's reply always is one. Group chat runs while this
page's server runs. Queued hand-offs, and replies that arrive while it is stopped (up to 24 hours), are passed on
when it starts again.

## Good to know

- An idle Codex **app** session reads a message only on its next turn: Reason cannot start a turn in the Codex app,
  and nothing else can while the app has the conversation open. For an agent that should answer on its own, use
  [auto-wake](#auto-wake) on a conversation the app does not have open.
  The composer says so and offers **Start a worker in its folder**; workers answer right away.
- The timeline shows messages that passed through this computer. On a multi-computer network, each computer sees its own traffic.
- The page shows message text from your agents. It listens on 127.0.0.1 only, so other computers cannot open it.
  Actions (send, start, stop) need a token the page gets when it loads, so other websites cannot trigger them.
- An unofficial companion tool. Not made by or affiliated with Reason.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `database not found` on start | Reason Network is not installed or never ran. Run `reason network` once. |
| "Can't read sessions" at the top | `reason` is not on PATH. Set `REASON_BIN` to the full path of the CLI. |
| Send fails with a certificate error | Your network inspects TLS. Set `NODE_EXTRA_CA_CERTS` to your company root CA file. |
| "Restart the server" at the top | The server was started before an update and still runs the old code. Stop it and start it again. |
| Port 8765 is taken | Set `REASON_CHAT_PORT=8766` (also change it in `.claude/launch.json`). |

## License

[MIT](LICENSE)
