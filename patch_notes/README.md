# Patch notes

**English** · [한국어](README.ko.md) · [中文](README.zh-CN.md)

What changed in Reason Network Chat, newest first. Times are KST.
Each row links to its pull request; the first two commits went straight to `main`.

## 2026-10-24

| Time | Change | What changed |
|---|---|---|
| 00:25 | [#19](https://github.com/ehojune/Reason-Network-Chat/pull/19) | **Group-room hand-offs are never dropped.** Over a room's limit they wait in a queue and go out in order (**Send all now** releases them), limits are set per room (default 100 hops, 300 per 10 minutes, or none), and replies that arrive while the server restarts are still passed on. **Messages go only to the @mentioned members** (`@all` for everyone, or the room's default recipient); the page shows who will get it and suggests names after `@`. |

## 2026-10-23

| Time | Change | What changed |
|---|---|---|
| 23:44 | [#18](https://github.com/ehojune/Reason-Network-Chat/pull/18) | A second server can no longer start on a port that is already in use: on Windows the port is bound exclusively, and the new one exits with "Port 8765 is in use" instead of silently sharing it with a stale server. |
| 23:31 | [#17](https://github.com/ehojune/Reason-Network-Chat/pull/17) | Pick **permissions** when starting a session (default, or full access with a confirmation), and **change a running worker's model, effort and permissions** from its right-click menu. A Codex model change applies from the next message; other changes restart the worker under the same name. Claude worker effort now actually applies. |
| 22:07 | [#16](https://github.com/ehojune/Reason-Network-Chat/pull/16) | An unread message sent with **Don't wake** (`--fyi`) now says *sent without waking · read on its next turn* instead of the session's usual "gets it right away", which it never did for such messages. |
| 21:41 | [#15](https://github.com/ehojune/Reason-Network-Chat/pull/15) | The agent badge (codex, claude-code, …) now also shows in front of each recipient, after the arrow. |
| 21:39 | [#14](https://github.com/ehojune/Reason-Network-Chat/pull/14) | **Auto-wake** a Codex session when a message arrives (right-click → Turn on auto-wake), so agents can work back and forth on their own. It spends Codex turns automatically, at most one a minute and 12 an hour per session. A conversation the Codex app has open cannot be woken; the page only flags it. |
| 19:01 | [#13](https://github.com/ehojune/Reason-Network-Chat/pull/13) | **Wake** a sleeping Codex session from the page: it runs one turn in that session's own conversation (`codex exec resume`) so it reads its unread messages and replies. Also as **Wake after sending**. |
| 18:53 | [#12](https://github.com/ehojune/Reason-Network-Chat/pull/12) | The line between the list and the chat can be dragged (or moved with ←/→ when focused); the width is kept by the server, and a double-click resets it. |
| 18:48 | [#11](https://github.com/ehojune/Reason-Network-Chat/pull/11) | Right-click a session or room (or Shift+F10) to pin it as a favorite at the top of the list; favorites are kept by the server. |
| 18:45 | [#10](https://github.com/ehojune/Reason-Network-Chat/pull/10) | Each session says in plain words how a message reaches it (answers right away, reads on its next turn, offline, …) on its row, in **To** and under unread bubbles. Offline and past sessions are hidden by default; sending to an offline one asks first. |
| 18:42 | [#9](https://github.com/ehojune/Reason-Network-Chat/pull/9) | A page that meets a server started before an update now says "Restart the server" instead of failing with a script error; missing fields no longer break it. |
| 17:40 | [#5](https://github.com/ehojune/Reason-Network-Chat/pull/5) | Group chat: members of a group room hear each other, and `@name` in a reply hands it to that member, with hop and rate limits so agents cannot talk in circles. |
| 17:40 | [#4](https://github.com/ehojune/Reason-Network-Chat/pull/4) | **+ Room** groups a few sessions: the room shows only their messages, and one send reaches every member. |
| 17:40 | [#3](https://github.com/ehojune/Reason-Network-Chat/pull/3) | **+ New session** starts an agent from the page: pick a folder and an agent, then a model and an effort from that agent's own list; run it as a network worker or in a terminal window. Codex sessions that a message cannot wake are marked, with a one-click worker in the same folder. |
| 17:32 | [#2](https://github.com/ehojune/Reason-Network-Chat/pull/2) | Patch notes in English, Korean and Chinese, linked from a badge at the top of each README. |
| 16:43 | [#1](https://github.com/ehojune/Reason-Network-Chat/pull/1) | Renamed to Reason Network Chat (`ehojune/Reason-Network-Chat`). Card 1 and the taglines say "Claude, Codex and other agents". |
| 16:15 | [`1b3162c`](https://github.com/ehojune/Reason-Network-Chat/commit/1b3162c) | `/api/send` takes JSON only with a size limit; a slow poll can no longer overwrite a newer one. |
| 16:10 | [`634dc50`](https://github.com/ehojune/Reason-Network-Chat/commit/634dc50) | First release: every Reason Network message on this computer in one chat room, with a send box. |
