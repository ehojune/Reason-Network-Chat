<p align="center"><img src="favicon.svg" width="88" height="88" alt="Reason Network Chat rabbit icon"></p>
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

<p align="center">
  <img src="docs/screen.en.svg" width="880" alt="Reason Network Chat with sample data: sessions on the left with busy/idle status, chat bubbles in the middle, a send box at the bottom.">
</p>

## What you can do

Agent conversations are spread across separate windows. Bring them into one timeline, with controls beside the conversation.

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

## Install and run

You need Python 3.8+ and [Reason Network](https://reasonmachines.com/network), installed and signed in. No extra Python packages.

Ask your coding agent to follow [AGENTS.md](AGENTS.md):

```text
https://github.com/ehojune/Reason-Network-Chat set this up for me
```

Or install it yourself:

```bash
git clone https://github.com/ehojune/Reason-Network-Chat
cd Reason-Network-Chat
python server.py
```

Open <http://127.0.0.1:8765>. Stop a server running in your terminal with Ctrl+C.
In the Claude desktop app, open this folder in the Code tab and ask to open it in the browser pane.

## Try it

| You want to | Start here |
|---|---|
| Message an existing session | Select it on the left → check **To** → type and press Enter. Shift+Enter adds a line. |
| Create a worker that keeps answering | **+ New session** → folder and agent → **worker** → model and effort. |
| Change Codex speed | New session, or right-click a worker → **Change settings → Speed** → Inherit Codex settings, Standard or Fast. |
| Talk to several agents | **+ Room** → choose members → enable **Group chat** → send `@name task`. |
| Ask Gemini for a code review | [Set up a Gemini reviewer](docs/manual.md#gemini-reviewer), then send `@gemini-reviewer PR_URL` in the room. |
| Organize the list | Right-click → **Favorite**. Use **Edit order** beside a section title, then drag or press ↑/↓. Items stay in their section. |

Your messages come from `<your name>/terminal`; replies appear in the timeline.
Delivery timing depends on the session type and whether it is busy. Labels on session rows and under messages explain it.
See the [user manual](docs/manual.md) for all controls.

## Work together in a room

<p align="center">
  <img src="docs/group-chat.en.svg" width="880" alt="You send a message to the room. Reason Network Chat sends it to the members you @mention, with the room lines each one missed. A member's reply that names @b-codex is passed on to b-codex, and an answer goes back to the member who asked. Hand-offs over a room's limits are queued, not dropped.">
</p>

Choose the sessions needed for a project and save them as a room. A plain room collects conversations; enabling **Group chat** lets agents exchange messages too.

- Use **+ Room** to set a name and members, then enable **Group chat**.
- Send `@member task` to address that member. Without a mention, the room uses its configured **default recipient**.
- An agent's reply mentioning another member is passed to that member. Mentions in a 1:1 reply do not automatically enter a room.
- **Delivery records** sit below the original statement. Delivery and read receipts are separate from completing the requested work.

See the [room manual](docs/manual.md#rooms) for routing, limits and **May post first without proof**.

## Before you use it

- **Use a worker for persistent replies.** An idle app or CLI session may wait until its next turn to read. A conversation open in the Codex app cannot be woken from outside it. [Delivery](docs/manual.md#delivery)
- **Auto-wake and group chat spend agent turns.** Each recipient may run a turn. Fast uses more quota, with speed depending on the model and account. [Wake](docs/manual.md#wake) · [Fast](docs/manual.md#codex-fast)
- **Full access runs commands without asking.** This includes deletion, installation and network access. [Permissions and restarts](docs/manual.md#permissions)
- **Workers keep running after the server stops.** Use **Stop worker** to end one. Group-room relay and auto-wake need the server running.

Only messages passing through this computer appear. The server binds to `127.0.0.1`, reads Reason's database read-only, and checks a page token for sends, starts and stops. This is an unofficial tool, unaffiliated with Reason.

## Find a guide

| You need | Read |
|---|---|
| Sessions, workers, reboot recovery, Gemini reviews | [User manual: sessions](docs/manual.md#sessions) |
| Read labels, collapsed deliveries, mentions, posting without proof | [Delivery labels](docs/manual.md#delivery) · [Rooms](docs/manual.md#rooms) |
| Failed replies, damaged text, port and certificate errors | [Failure handling](docs/manual.md#recovery) · [Troubleshooting](docs/manual.md#troubleshooting) |
| Agent setup and development rules | [AGENTS.md](AGENTS.md) |
| API, configuration and implementation details | [Reference index](docs/reference/README.md) |
| Recent changes | [Patch notes](patch_notes/README.md) |

[MIT license](LICENSE)
