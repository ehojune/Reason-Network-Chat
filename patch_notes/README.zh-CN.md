# 更新日志

[English](README.md) · [한국어](README.ko.md) · **中文**

Reason Network Chat 的变更记录，最新的在前。时间为韩国时间（KST）。
每一行都链接到对应的 PR；最早的两个提交直接推到了 `main`。

## 2026-10-23

| 时间 | 变更 | 主要内容 |
|---|---|---|
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
