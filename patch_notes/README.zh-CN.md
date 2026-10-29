# 更新日志

[English](README.md) · [한국어](README.ko.md) · **中文**

Reason Network Chat 的变更记录，最新的在前。时间为韩国时间（KST）。
每一行都链接到对应的 PR；最早的两个提交直接推到了 `main`。

## 2026-10-29

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 16:23 | [#61](https://github.com/ehojune/Reason-Network-Chat/pull/61) | 通过版本、文件范围和空闲队列检查协调任务交接。 |
| 15:22 | [#62](https://github.com/ehojune/Reason-Network-Chat/pull/62) | 在三种语言的 README 标题中说明智能体聊天界面用途，并以文字显示功能摘要。 |
| 14:55 | [#60](https://github.com/ehojune/Reason-Network-Chat/pull/60) | 显示已保存的批次回复及已验证的共同回复，防止重新执行旧请求。 |
| 13:35 | [#58](https://github.com/ehojune/Reason-Network-Chat/pull/58) | 将受管理 worker 上限增至 12，可保留两位负责人和六个 worker 并启动审查器。 |
| 05:05 | [#57](https://github.com/ehojune/Reason-Network-Chat/pull/57) | Gemini 审查器不再把仅引用其名字的通知当作请求，每次提示都带上运作规则，超时可配置，失败时报告原因和日志路径。 失败通知保留已发布审查的证据。 |

## 2026-10-27

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 17:26 | [#55](https://github.com/ehojune/Reason-Network-Chat/pull/55) | Gemini 接收器在首次对话前即可显示并邀请进入房间；Gemini 徽章改为紫色。 |
| 16:15 | [#54](https://github.com/ehojune/Reason-Network-Chat/pull/54) | Codex 批次只保留一份重复的投递说明，同时完整保留消息原文、上下文和路由信息。 |
| 10:20 | [#53](https://github.com/ehojune/Reason-Network-Chat/pull/53) | Codex 可选择合并同一聊天室的待处理消息，优先读取用户指令，并保留原文及持久化送达记录。 |

## 2026-10-26

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 21:33 | [#52](https://github.com/ehojune/Reason-Network-Chat/pull/52) | 仅含运行日志的 Codex 回复显示为可展开提示，不再转发、重发旧转发副本或加入群聊上下文。 |
| 17:23 | [#51](https://github.com/ehojune/Reason-Network-Chat/pull/51) | README 恢复六张带说明的功能卡片和群聊转发示意图，详细操作仍放在独立手册中。 |
| 16:14 | [#50](https://github.com/ehojune/Reason-Network-Chat/pull/50) | 精简 README，按任务查阅用户手册；智能体操作、API 和实现细节移至参考文档。 |
| 14:50 | [#49](https://github.com/ehojune/Reason-Network-Chat/pull/49) | Codex 新会话和设置窗口支持继承速度、Standard 或 Fast；实时更改从下一条消息生效，并在重启时保留。 |
| 12:51 | [#48](https://github.com/ehojune/Reason-Network-Chat/pull/48) | Gemini 读取转发记录时与写入方共用锁，确保 Windows 可在接收器运行期间保存新群聊投递。 |
| 12:00 | [#47](https://github.com/ehojune/Reason-Network-Chat/pull/47) | 群聊提及可调用持久 Gemini 审查器；PR 请求返回 P0–P3 问题及 Gemini GitHub App 发布的审查链接。 |
| 10:41 | [#45](https://github.com/ehojune/Reason-Network-Chat/pull/45) | 通过拖动手柄或上下按钮调整侧栏顺序。排序仅限当前分类，刷新后保留。 |
| 03:38 | [#44](https://github.com/ehojune/Reason-Network-Chat/pull/44) | 疑似编码损坏会阻止发送、重发或重试已保存的转发封装；增加发布前离线文件检查并说明保护范围，三种语言的 README 均展示现有兔子图标。 |

## 2026-10-24

| 时间 | 变更 | 主要内容 |
|---|---|---|
| 06:08 | [#43](https://github.com/ehojune/Reason-Network-Chat/pull/43) | 侧栏各分区可通过灰色文字单独收起并保留状态。新增长兔耳六边形标签图标，收藏中的 worker 菜单说明自动接收消息。 |
| 05:44 | [#41](https://github.com/ehojune/Reason-Network-Chat/pull/41) | 聊天室只显示一次发言，下方列出转发记录；代码或引用中的 @ 不再唤醒成员，已证实的消息副本回复会关联回原聊天室。 |
| 03:58 | [#39](https://github.com/ehojune/Reason-Network-Chat/pull/39) | 发送后崩溃会核对记录，避免重复转发；结果不明确时等待检查。加固 worker 注册表并发保存、进程清理、模型识别，以及房间身份和目录刷新验证。 |
| 03:18 | [#36](https://github.com/ehojune/Reason-Network-Chat/pull/36) | 成员可通过 `rnc.py room send` **主动发消息**，定时报告无需等待用户先发消息。支持 Windows、Linux、macOS 的发送者验证，并在重启后保留房间授权。 |
| 03:02 | [#38](https://github.com/ehojune/Reason-Network-Chat/pull/38) | **查看**失败或未回答消息的原文、接收者和失败详情，再逐条处理。引用可跳到原文，无回答回复折叠为确认标记；修复 Markdown 链接、列表代码块和用量限制通知的转发循环。 |
| 02:47 | [#35](https://github.com/ehojune/Reason-Network-Chat/pull/35) | **能识别卡住的 worker**（忙碌 30 分钟以上且步骤没有变化）：右键菜单可查看其下运行的进程，并以相同设置**重新启动**。智能体用 **`python rnc.py worker start/restart/stop/adopt`** 管理 worker，不再在自己的回合里启动 worker。 |
| 02:41 | [#31](https://github.com/ehojune/Reason-Network-Chat/pull/31) | **worker 的失败不再当作回答转发**（曾在失败的 worker 之间半分钟内来回 36 次）：显示为红色提示，你的消息带 **再次发送**。worker 已读未答的消息也会标出，消息框上方一行汇总并提供 **全部再次发送**。 |
| 01:55 | [#30](https://github.com/ehojune/Reason-Network-Chat/pull/30) | 转发的回复（↪ … 的回复已转给）现在**显示转发的内容**：标记下方显示开头几行，点击后按格式完整展开。收到它的成员的 1:1 视图里原来只有标记，现在也一样能看到。 |
| 01:40 | [#29](https://github.com/ehojune/Reason-Network-Chat/pull/29) | **区分 1:1 与聊天室。** 给群聊成员发 1:1 消息时，消息框上方显示 1:1 提示和聊天室链接，智能体也会收到一行说明：回答里的 @ 不会被转发。成员的 1:1 回答里 @ 了其他成员时，可用 **转发到聊天室** 转发一次，效果如同在聊天室里回答。 |
| 01:25 | [#28](https://github.com/ehojune/Reason-Network-Chat/pull/28) | 群聊中**成员的回答无需 @ 也会自动回到提问的成员**（只回一层，避免两个智能体无休止地互相道谢）；`-` 或 `(해당 없음)` 表示无需回答，不发给任何人。消息上的 **↩** 可带引用回复作者。回合中途被停止的 worker 现在显示为*已停止（网络上仅剩记录）*，而不是忙碌。 |
| 00:51 | [#25](https://github.com/ehojune/Reason-Network-Chat/pull/25) | worker 的**最后设置在重启电脑后依然保留**：已停止的 worker 仍显示 codex / claude-code 标记（而不是 "cli"），**重新启动**（单个、聊天室或全部）经一次确认即可以相同的模型、推理强度和权限恢复。worker 的内部会话在列表中折叠隐藏。 |
| 00:41 | [#22](https://github.com/ehojune/Reason-Network-Chat/pull/22) | 消息以 **Markdown** 显示：表格（在气泡内滚动）、粗体和斜体、代码、列表、标题、引用和链接。点气泡下方的**原文**可查看原始文字。 |
| 00:34 | [#20](https://github.com/ehojune/Reason-Network-Chat/pull/20) | 本页启动但从列表中丢失的 worker 会被**重新接管**（每 30 秒从运行中的进程里查找），因此 Claude worker 也能再次**更改设置**；在别处启动的 worker 经确认后也可在本页管理。 |
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
