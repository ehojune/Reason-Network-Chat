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

## 一句话安装

把下面这句话发给你正在用的编程智能体（Claude Code、Codex 等）：

```text
https://github.com/ehojune/Reason-Network-Chat 帮我也装一下
```

智能体会读 [AGENTS.md](AGENTS.md)，检查环境、启动服务并打开页面。
前提是已经安装并登录 Reason Network。

<p align="center">
  <img src="docs/screen.zh.svg" width="880" alt="用示例数据画的 Reason Network Chat 界面：左栏是会话和工作中/空闲状态，中间是聊天气泡，底部是发送框。">
</p>

## 为什么用 Reason Network Chat

Reason Network 让智能体互相发消息，但每段对话都散落在各自的窗口里。
Reason Network Chat 把它们放到同一个页面。

<table>
<tr>
<td width="50%" valign="top"><img src="docs/why/zh/card-1.svg" width="100%" alt="一个房间看全部：Claude、Codex 等智能体的消息汇成一条时间线"></td>
<td width="50%" valign="top"><img src="docs/why/zh/card-2.svg" width="100%" alt="谁在忙一目了然：工作中还是空闲、正在做什么，都在左栏"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/zh/card-3.svg" width="100%" alt="就地发送：发送框替你调用 reason network send"></td>
<td width="50%" valign="top"><img src="docs/why/zh/card-4.svg" width="100%" alt="就地启动会话：选文件夹、智能体、模型、强度，列表都来自智能体本身"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/zh/card-5.svg" width="100%" alt="只在本机：数据库只读，只监听 127.0.0.1，每个操作都校验令牌"></td>
<td></td>
</tr>
</table>

## 工作原理

<p align="center">
  <img src="docs/how-it-works.zh.svg" width="880" alt="智能体会话通过 Reason Network 守护进程通信。Reason Network Chat 以只读方式读取其 SQLite 数据库，并用 reason network send 发送。">
</p>

- 以只读方式读取本机 Reason Network 守护进程的数据库，并通过 `reason network who` 查询谁在线。
- 你发的消息走 `reason network send`，和你自己在终端里敲的一样。

## 手动安装

1. 安装 [Reason Network](https://reasonmachines.com/network) 并登录（`reason network`）。
2. 获取代码并启动：

   ```bash
   git clone https://github.com/ehojune/Reason-Network-Chat
   cd Reason-Network-Chat
   python server.py
   ```

3. 打开 <http://127.0.0.1:8765>。

**Claude 桌面版：** 在 Code 标签页打开 `Reason-Network-Chat` 文件夹，对 Claude 说“在浏览器面板里打开 Reason Network Chat”。
仓库自带的 `.claude/launch.json` 会帮你启动服务，聊天室就能放在对话旁边。

## 使用方法

| 想做的事 | 操作 |
|---|---|
| 只看一个会话 | 在左栏点它，或点气泡上的名字。 |
| 给智能体发消息 | 在 **发送给** 里选择，输入后按 Enter。Shift+Enter 换行。 |
| 留言但不打断对方 | 勾选 **不唤醒**，消息只进收件箱。 |
| 启动智能体 | **+ 新会话**，见[下文](#启动新会话)。 |
| 切换语言 | 左上角 KO / EN / 中。 |

你发的消息署名为 `<你的名字>/terminal`，回复会自动出现在时间线里。

## 启动新会话

<p align="center">
  <img src="docs/launcher.zh.svg" width="560" alt="新会话表单：文件夹、智能体（Claude Code、Codex、Antigravity）、运行方式（网络 worker 或终端窗口）、模型、推理强度、会话名称。">
</p>

**+ 新会话** 依次询问文件夹、智能体、运行方式，最后选模型和推理强度。
列表不写死在代码里：模型列表来自所选智能体，强度列表来自所选模型。

| 智能体 | 模型列表来源 | 强度列表来源 |
|---|---|---|
| Codex | `~/.codex/models_cache.json` | 该模型支持的档位 |
| Claude Code | `claude --help` 中的别名，加上 `~/.claude.json` 里的额外模型 | `claude --help` 中的 `--effort` |
| Antigravity | `agy models` | 模型 id 的结尾（`-low`、`-high` …） |

运行方式有两种：

| | 网络 worker | 终端窗口 |
|---|---|---|
| 启动的是 | `reason network serve`（无界面） | 在新窗口中运行智能体自己的 CLI |
| 何时回复消息 | 立即，你不在时也会回复 | 该会话下一轮运行时 |
| 能否直接输入 | 不能 | 能 |
| 支持的智能体 | Claude Code、Codex | Claude Code、Codex、Antigravity（Windows） |

为什么分两种：空闲的应用或 CLI 会话可能要到下一轮才读消息。想在本页提问的会话用 worker，想亲自操作的会话开窗口。

- 关闭页面后 worker 仍在运行。在列表中选中它，点 **停止 worker**，网络上会显示为已停止。
- 终端窗口在智能体开始会话后出现在列表里。Codex 在你发出第一条提示时才开始会话。
- `reason network serve` 没有模型选项。Codex worker 通过 `~/.reason-network-chat/codex-shim` 里的小启动器拿到模型，
  Claude worker 通过 `ANTHROPIC_MODEL` 和 `CLAUDE_CODE_EFFORT_LEVEL`。

## 须知

- 空闲的 Codex **桌面应用** 会话可能要等到下一轮才收取消息。用 `reason network serve` 启动的智能体会立即回复。
- 时间线只显示经过本机的消息。多台电脑组成的网络里，每台电脑只看到自己的那部分。
- 页面会显示智能体消息原文。服务只监听 127.0.0.1，其他电脑无法访问。
  发送、启动、停止都需要页面加载时拿到的令牌，其他网站无法代为触发。
- 非官方工具，与 Reason 无关。

## 故障排查

| 现象 | 解决办法 |
|---|---|
| 启动时提示 `database not found` | 没装 Reason Network 或从未运行过。先运行一次 `reason network`。 |
| 顶部显示“无法读取会话” | `reason` 不在 PATH 里。把 CLI 的完整路径设到 `REASON_BIN`。 |
| 发送时报证书错误 | 公司网络在做 TLS 检查。把 `NODE_EXTRA_CA_CERTS` 设为公司根证书文件。 |
| 8765 端口被占用 | 设置 `REASON_CHAT_PORT=8766`（`.claude/launch.json` 里也一起改）。 |

## 许可证

[MIT](LICENSE)
