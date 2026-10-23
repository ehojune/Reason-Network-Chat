# 更新日志

[English](README.md) · [한국어](README.ko.md) · **中文**

Reason Network Chat 的变更记录，最新的在前。时间为韩国时间（KST）。
每一行都链接到对应的 PR；最早的两个提交直接推到了 `main`。

## 2026-10-24

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 00:25 | [#19](https://github.com/ehojune/Reason-Network-Chat/pull/19) | **群聊转发不再丢弃。** 超过聊天室上限时排队按顺序发出（**全部立即发送**可立即放行），上限按聊天室设置（默认 100 跳、每 10 分钟 300 次，或不限），服务器重启期间到达的回复也会继续转发。**消息只发给被 @ 的成员**（`@all` 为全体，或聊天室的默认接收成员）；页面会显示谁将收到，并在 `@` 后提示名称。 |

## 2026-10-23

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 23:44 | [#18](https://github.com/ehojune/Reason-Network-Chat/pull/18) | 已占用的端口上无法再启动第二个服务器：Windows 上独占绑定端口，新服务器会以 "Port 8765 is in use" 退出，而不是悄悄与旧服务器共用端口。 |
| 23:31 | [#17](https://github.com/ehojune/Reason-Network-Chat/pull/17) | 启动会话时可选择**权限**（默认，或经确认的完全权限），并可从右键菜单**更改运行中 worker 的模型、推理强度和权限**。Codex 的模型更改从下一条消息起生效，其他更改会以同一名称重启 worker。Claude worker 的推理强度现在真正生效。 |
| 22:07 | [#16](https://github.com/ehojune/Reason-Network-Chat/pull/16) | 用**不唤醒**（`--fyi`）发送的未读消息，现在显示 *未唤醒发送 · 下一轮才读*，而不是会话平时的“立即收到”——这类消息本来就不会立即送达。 |
| 21:41 | [#15](https://github.com/ehojune/Reason-Network-Chat/pull/15) | 箭头后的每个接收会话前也会显示智能体标记（codex、claude-code 等）。 |
| 21:39 | [#14](https://github.com/ehojune/Reason-Network-Chat/pull/14) | 收到消息时**自动唤醒** Codex 会话（右键 → 开启自动唤醒），智能体之间可以自行来回协作。它会自动消耗 Codex 轮次，每个会话每分钟最多一次、每小时最多 12 次。Codex 应用正打开的对话无法唤醒，页面只会标注。 |
| 19:01 | [#13](https://github.com/ehojune/Reason-Network-Chat/pull/13) | 可在页面上**唤醒**沉睡的 Codex 会话：在它自己的对话中运行一轮（`codex exec resume`），读取未读消息并回复。也可选择**发送后唤醒**。 |
| 18:53 | [#12](https://github.com/ehojune/Reason-Network-Chat/pull/12) | 列表与聊天之间的分隔线可以拖动（选中后也可按 ←/→）；宽度由服务器保存，双击恢复默认。 |
| 18:48 | [#11](https://github.com/ehojune/Reason-Network-Chat/pull/11) | 右键点击会话或聊天室（或按 Shift+F10）即可收藏并置顶在列表顶部；收藏由服务器保存。 |
| 18:45 | [#10](https://github.com/ehojune/Reason-Network-Chat/pull/10) | 每个会话在列表、**发送给** 和未读气泡下方用浅白的话标出消息如何送达（立即回复、下一轮才读、离线……）。离线和过往会话默认隐藏；向离线会话发送前会先确认。 |
| 18:42 | [#9](https://github.com/ehojune/Reason-Network-Chat/pull/9) | 遇到更新前启动的服务器时，页面不再因脚本错误崩溃，而是提示“请重启服务器”；缺少字段也不会出错。 |
| 17:40 | [#5](https://github.com/ehojune/Reason-Network-Chat/pull/5) | 群聊：群聊聊天室的成员彼此都能听到；回复中写 `@名称` 会转给该成员，并有接力和频率上限，避免智能体无休止地互聊。 |
| 17:40 | [#4](https://github.com/ehojune/Reason-Network-Chat/pull/4) | **+ 聊天室** 把几个会话放在一起：只显示它们的消息，发一次即送达全体成员。 |
| 17:40 | [#3](https://github.com/ehojune/Reason-Network-Chat/pull/3) | **+ 新会话** 可在页面上启动智能体：选文件夹和智能体后，从该智能体自己的列表里选模型和强度，以网络 worker 或终端窗口运行。不会被消息唤醒的 Codex 会话会被标出，并可一键在同一文件夹启动 worker。 |
| 17:32 | [#2](https://github.com/ehojune/Reason-Network-Chat/pull/2) | 新增英文、韩文、中文更新日志，并在每个 README 顶部放了徽章链接。 |
| 16:43 | [#1](https://github.com/ehojune/Reason-Network-Chat/pull/1) | 更名为 Reason Network Chat（`ehojune/Reason-Network-Chat`）。卡片 1 和简介改为“Claude、Codex 等智能体”。 |
| 16:15 | [`1b3162c`](https://github.com/ehojune/Reason-Network-Chat/commit/1b3162c) | `/api/send` 只接受有大小限制的 JSON；较慢的轮询响应不会再覆盖较新的响应。 |
| 16:10 | [`634dc50`](https://github.com/ehojune/Reason-Network-Chat/commit/634dc50) | 首次发布：把本机 Reason Network 上的消息汇进一个聊天室，并提供发送框。 |
