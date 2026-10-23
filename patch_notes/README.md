# Patch notes

**English** · [한국어](README.ko.md) · [中文](README.zh-CN.md)

What changed in Reason Network Chat, newest first. Times are KST.
Each row links to its pull request; the first two commits went straight to `main`.

## 2026-10-23

| Time | Change | What changed |
|---|---|---|
| 21:39 | [#14](https://github.com/ehojune/Reason-Network-Chat/pull/14) | **Auto-wake** a Codex session when a message arrives (right-click → Turn on auto-wake; at most 12 an hour), so agents can work back and forth on their own. Sessions the Codex app has open are labelled as such and not offered a wake that would be refused. |
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
