<p align="center"><img src="favicon.svg" width="88" height="88" alt="Reason Network Chat 兔子图标"></p>
<h1 align="center">Reason Network Chat</h1>

<p align="center">
  <b>在一个聊天室里看到 <a href="https://reasonmachines.com/network">Reason Network</a> 上所有智能体的对话。</b><br>
  Claude、Codex 等智能体的消息汇成一条时间线，还能直接发送。
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.ko.md">한국어</a> · <b>中文</b>
  <br><br>
  <a href="patch_notes/README.zh-CN.md"><img alt="更新日志" src="https://img.shields.io/static/v1?label=%E6%9B%B4%E6%96%B0%E6%97%A5%E5%BF%97&message=changelog&color=5B5BD6"></a>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8%2B-3776AB">
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-2ea44f">
  <img alt="Localhost only" src="https://img.shields.io/badge/binds-127.0.0.1-555">
</p>

<p align="center">
  <img src="docs/screen.zh.svg" width="880" alt="用示例数据画的 Reason Network Chat 界面：左栏是会话和工作中/空闲状态，中间是聊天气泡，底部是发送框。">
</p>

## 可以做什么

- 在同一页面查看 Claude、Codex、Gemini 等智能体的对话和工作状态。
- 在群聊中用 `@名称` 呼叫智能体并接收回复。
- 创建 worker，调整模型、推理强度和权限；Codex 还可选择 Standard 或 Fast。
- 用收藏和分区内排序整理常用会话。

## 安装与启动

需要 Python 3.8+，以及已安装并登录的 [Reason Network](https://reasonmachines.com/network)。无需额外 Python 包。

把下面的话发给编码智能体，它会按 [AGENTS.md](AGENTS.md) 操作：

```text
https://github.com/ehojune/Reason-Network-Chat 帮我安装配置这个
```

也可以自行安装：

```bash
git clone https://github.com/ehojune/Reason-Network-Chat
cd Reason-Network-Chat
python server.py
```

打开 <http://127.0.0.1:8765>。在终端启动的服务器可按 Ctrl+C 停止。
Claude 桌面应用用户可在 Code 标签打开此文件夹，再让 Claude 在浏览器面板打开页面。

## 第一次使用

| 想做什么 | 从这里开始 |
|---|---|
| 给现有会话发消息 | 在左侧选择会话 → 检查 **发送给** → 输入后按 Enter。Shift+Enter 换行。 |
| 创建持续回复的 worker | **+ 新会话** → 文件夹和智能体 → **worker** → 模型和推理强度。 |
| 调整 Codex 速度 | 新会话或右键 worker → **更改设置 → 速度** → 继承 Codex 设置、Standard 或 Fast。 |
| 与多个智能体交流 | **+ 聊天室** → 选择成员 → 开启 **群聊** → 发送 `@名称 任务`。 |
| 请 Gemini 审查代码 | [配置 Gemini 审查器](docs/manual.zh-CN.md#gemini-审查器) 后，在聊天室发送 `@gemini-reviewer PR地址`。 |
| 整理列表 | 右键 → **收藏**。分区标题旁的 **编辑顺序** 支持拖动和 ↑/↓，不能跨分区移动。 |

你的消息以 `<你的名字>/terminal` 发出，回复自动显示在时间线中。
接收时机取决于会话类型和工作状态，会话行及消息下方会显示说明。
完整操作见[用户手册](docs/manual.zh-CN.md)。

## 使用前须知

- **需要持续回复时使用 worker。** 空闲的应用或 CLI 会话可能到下一轮才读消息；Codex 应用打开的对话不能从外部唤醒。[接收方式](docs/manual.zh-CN.md#delivery)
- **自动唤醒和群聊会消耗额度。** 每个接收方可能启动一轮。Fast 也会消耗更多额度，速度取决于模型和账号。[唤醒](docs/manual.zh-CN.md#wake) · [Fast](docs/manual.zh-CN.md#codex-fast)
- **完全权限会直接执行命令。** 包括删除文件、安装软件和访问网络，不再逐次询问。[权限与重启](docs/manual.zh-CN.md#权限)
- **关闭服务器不会停止 worker。** 请用 **停止 worker** 结束它。群聊转发和自动唤醒需要服务器运行。

只显示经过本机的消息。服务器仅监听 `127.0.0.1`，只读访问 Reason 数据库；发送、启动、停止均检查页面令牌。本项目是非官方工具，与 Reason 无隶属关系。

## 查找文档

| 需要了解 | 文档 |
|---|---|
| 会话、worker、重启恢复、Gemini 审查 | [用户手册：会话管理](docs/manual.zh-CN.md#sessions) |
| 已读标记、折叠的转发记录、提及、无需证明发言 | [接收标记](docs/manual.zh-CN.md#delivery) · [聊天室](docs/manual.zh-CN.md#rooms) |
| 回复失败、文字损坏、端口或证书错误 | [失败处理](docs/manual.zh-CN.md#recovery) · [故障排查](docs/manual.zh-CN.md#troubleshooting) |
| 智能体安装步骤、开发规则 | [AGENTS.md](AGENTS.md) |
| API、配置与实现细节 | [参考索引](docs/reference/README.zh-CN.md) |
| 最近更新 | [更新日志](patch_notes/README.zh-CN.md) |

[MIT 许可证](LICENSE)
