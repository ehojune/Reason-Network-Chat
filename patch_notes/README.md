# Patch notes

**English** · [한국어](README.ko.md) · [中文](README.zh-CN.md)

What changed in Reason Network Chat, newest first. Times are KST.
Each row links to its pull request; the first two commits went straight to `main`.

## 2026-10-26

| Time | Change | What changed |
|---|---|---|
| 03:38 | [#44](https://github.com/ehojune/Reason-Network-Chat/pull/44) | Suspected encoding damage blocks chat sends and relays; an offline file checker explains the external-post boundary, and every README shows the existing rabbit icon. |

## 2026-10-24

| Time | Change | What changed |
|---|---|---|
| 06:08 | [#43](https://github.com/ehojune/Reason-Network-Chat/pull/43) | Sidebar sections collapse independently with gray text and remember their state. A long-eared hexagon favicon marks the tab; favorite worker menus explain automatic delivery. |
| 05:44 | [#41](https://github.com/ehojune/Reason-Network-Chat/pull/41) | Room statements show once with delivery records underneath; quoted/code mentions no longer wake members, and replies to proven envelope copies retain their room. |
| 03:58 | [#39](https://github.com/ehojune/Reason-Network-Chat/pull/39) | Queued hand-offs recover after a crash without silently sending twice; uncertain delivery waits for inspection. Multiple servers preserve worker registries, model detection ignores tools, adopted workers clean up their verified children, and room identity/catalog refresh are guarded. |
| 03:18 | [#36](https://github.com/ehojune/Reason-Network-Chat/pull/36) | Members can **post first** with `rnc.py room send`: scheduled reports no longer need a person to send a room message first. Sender proof works on Windows, Linux and macOS; explicit room permissions survive a restart. |
| 03:02 | [#38](https://github.com/ehojune/Reason-Network-Chat/pull/38) | **View** shows failed/unanswered messages before retrying: originals, recipients and failure details. Reply quotes jump to the original; no-answer replies fold into acknowledgements. Markdown links/list fences and usage-limit relay loops are fixed. |
| 02:47 | [#35](https://github.com/ehojune/Reason-Network-Chat/pull/35) | **A stuck worker shows as such** (busy 30 minutes with no new step) and its right-click menu shows what runs under it and **restarts** it with the same settings. **`python rnc.py worker start/restart/stop/adopt`** is the supported way for agents to manage workers, so none is started inside an agent's own turn again. |
| 02:41 | [#31](https://github.com/ehojune/Reason-Network-Chat/pull/31) | **A worker's failure is no longer passed on as an answer** (it once bounced between failing workers 36 times in half a minute): it shows as a red notice, and your message gets **Send again**. Messages a worker read but never answered are marked too, and a bar lists both for the room with **Send all again**. |
| 01:55 | [#30](https://github.com/ehojune/Reason-Network-Chat/pull/30) | A passed-on reply (↪ … passed to …) now shows **what was passed on**: its first lines under the marker, and the whole reply, formatted, on a click. Also in the 1:1 view of the member who got it, where the marker used to be all there was. |
| 01:40 | [#29](https://github.com/ehojune/Reason-Network-Chat/pull/29) | **1:1 and the room are told apart.** Writing to one session that is in a group room shows a 1:1 notice with a link to the room, and the agent gets a one-line note that its @mentions will not be passed on. A member's 1:1 answer that @mentions others gets **Forward to room**, which passes it on once, as if it had answered in the room. |
| 01:25 | [#28](https://github.com/ehojune/Reason-Network-Chat/pull/28) | In a group room **a member's answer goes back to the member who asked**, without an @mention (one level, so two agents cannot thank each other in circles); `-` or `(해당 없음)` means no answer and goes nowhere. **↩** on a message answers its author with a quote. A worker stopped mid-turn now shows as *stopped (only the network's entry is left)* instead of busy. |
| 00:51 | [#25](https://github.com/ehojune/Reason-Network-Chat/pull/25) | Workers keep their **last settings after a reboot**: a stopped worker keeps its codex / claude-code badge (not "cli"), and **Start again** (one, a room's, or all) brings it back with the same model, effort and access after one confirmation. A worker's own inner sessions are folded away from the list. |
| 00:41 | [#22](https://github.com/ehojune/Reason-Network-Chat/pull/22) | Messages render **Markdown**: tables (scrolling inside the bubble), bold and italics, code, lists, headings, quotes and links. **Source** under a bubble shows the text as written. |
| 00:34 | [#20](https://github.com/ehojune/Reason-Network-Chat/pull/20) | Workers this page started but lost from its list are **taken back** (found among running processes every 30 s), so **Change settings** works for them again, Claude workers included; a worker started elsewhere can be managed here after a confirmation. |
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
