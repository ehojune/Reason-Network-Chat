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
<td width="50%" valign="top"><img src="docs/why/en/card-5.svg" width="100%" alt="Local and guarded: database read-only, 127.0.0.1 only, a token on every action"></td>
<td></td>
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
| Switch language | KO / EN / 中 at the top left. |

Messages you send come from `<your name>/terminal`. Replies show up in the timeline on their own.

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

- A worker keeps running after you close the page. Select it and press **Stop worker**; the network shows it as stopped.
- A terminal window joins the list once the agent starts its session. Codex starts it with your first prompt.
- `reason network serve` has no model option. A Codex worker gets its model through a small launcher in
  `~/.reason-network-chat/codex-shim`; a Claude worker through `ANTHROPIC_MODEL` and `CLAUDE_CODE_EFFORT_LEVEL`.

## Good to know

- An idle Codex **app** session may not pick up a message until its next turn. Agents started with `reason network serve` answer right away.
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
| Port 8765 is taken | Set `REASON_CHAT_PORT=8766` (also change it in `.claude/launch.json`). |

## License

[MIT](LICENSE)
