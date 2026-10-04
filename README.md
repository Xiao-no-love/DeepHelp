# DeepHelp

[中文](#中文) · [English](#english)

> 一个具备本地操作能力的 AI 助手。以 `pywebview` 构建界面，用 `Playwright` 通过 CDP 驱动浏览器与 DeepSeek 对话，把自然语言转化为真实的文件读写、命令执行与本地操作。

[![version](https://img.shields.io/badge/version-0.7.0-informational)](#)
[![platform](https://img.shields.io/badge/platform-Windows-informational)](#)
[![license](https://img.shields.io/badge/license-MIT-informational)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-informational)](#)

---

# 中文

## 简介

DeepHelp 把大语言模型接入本地系统。你在界面里用自然语言下达指令，模型通过动作标签调用本地技能——读写文件、执行命令、打补丁、管理后台服务——结果回传模型，循环推进，直到任务完成。

所有动作在本地执行，模型只负责决策。

## 特性

- **本地 GUI**：`pywebview`（WebView2）无边框界面，纯 Web 技术构建
- **AI 驱动**：`Playwright` 经 CDP 连接 Chrome，操控 DeepSeek 网页版
- **17 种内置动作**：文件读写、命令执行、Python 执行、智能补丁、服务管理、会话标题等
- **可插拔技能**：`actions/` 下每个技能独立成模块，新增技能 = 放入一个 `.py`，内核零改动
- **流式交错展示**：文字与工具卡片按模型原文顺序铺开
- **自动模式**：模型停下时自动续接推进，达成目标或达轮数上限自动停止
- **消息排队**：忙碌时仍可输入，消息自动并入下一轮
- **会话本地化**：对话流水以 JSONL 落盘（`chat_logs/`），支持历史会话列表与一键恢复
- **Markdown 渲染**：表格、代码高亮、列表与引用完整排版
- **可定制外观**：背景图、卡片模糊度、字号实时调节
- **单文件分发**：PyInstaller 打包为免安装单 exe

## 架构

```
┌─────────────┐   JS↔Python   ┌──────────────┐   CDP    ┌──────────┐
│  webui/     │ ◄───────────► │   api.py     │ ◄──────► │  Chrome  │
│ (pywebview) │   evaluate_js │  (桥接调度)   │          │ DeepSeek │
└─────────────┘               └──────┬───────┘          └──────────┘
                                     │
                              ┌──────┴───────┐
                              │   agent.py   │  Playwright 驱动
                              │  action.py   │  动作解析与执行
                              └──────┬───────┘
                                     │ 动态加载
                              ┌──────┴───────┐
                              │  actions/*.py │  17 个技能
                              └──────────────┘
```

工作流：**用户消息 → 模型回复 → 解析动作标签 → 本地执行 → 结果回传 → 模型继续**，循环直到任务完成。

## 项目结构

```
optimize/
├── main.pyw            # 入口（单实例锁 + HTTP 服务器加固）
├── api.py              # pywebview JS↔Python 桥接层（任务调度）
├── agent.py            # DeepSeek 浏览器代理（Playwright 操控）
├── action.py           # 动作解析与执行内核
├── chatlog.py          # 会话流水记录（JSONL，本地化）
├── config.py           # 默认配置 + 系统提示组装
├── prompt.py           # 人设/规则/笔记管理（prompt.json）
├── actions/            # 可插拔技能（每个 .py 一个技能）
├── webui/              # 前端界面（原生 HTML/CSS/JS）
│   ├── demo.html
│   ├── css/            # main.css / body.css
│   ├── js/             # app.js / init.js
│   └── vendor/         # marked / DOMPurify / highlight.js / FontAwesome
├── deephelp.spec       # PyInstaller 打包配置
├── version_info.txt    # exe 版本信息
└── requirements.txt
```

## 内置动作

| 动作 | 说明 | 关键参数 |
|---|---|---|
| `python` | 执行 Python 代码 | `cwd` |
| `shell` | 执行 Shell 命令 | `cwd`、`timeout` |
| `file_read` | 读取文件 | `file`、`max_chars` |
| `file_write` | 写入（覆盖） | `file` |
| `file_append` | 追加到末尾 | `file` |
| `file_delete` | 删除文件/目录 | `file` |
| `dir_list` | 列出目录 | `path` |
| `replace_lines` | 按行号替换，支持多段 `@@` 头 | `file`、`start`、`end`、`expect` |
| `smart_patch` | unified diff 补丁（预校验 → 应用 → 校验 + 回滚） | `file`、`context` |
| `python_reset` | 重置 Python 执行环境 | — |
| `auto_mode` | 开关自动模式 | body: `on` / `off` |
| `notice` | 弹出 Windows 系统通知 | `title`、`msg` |
| `prompt_edit` | 读写自身 `prompt.json` | `field`、`mode` |
| `service_list` | 列出托管的后台服务 | — |
| `service_log` | 查看后台服务日志 | `service`、`tail` |
| `service_stop` | 停止后台服务 | `service` |
| `set_chat_title` | 修改 DeepSeek 会话标题 | `title` |

> 每个动作结果默认回传（`replay` 默认 `true`），可用 `replay="false"` 关闭。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> `playwright install chromium` 非必需 —— 本程序连接的是系统已安装的 Chrome（调试端口），不依赖 Playwright 自带浏览器。

### 2. 准备 Chrome

程序通过 CDP 调试端口连接 Chrome。首次运行后在生成的 `config.json` 里填好 Chrome 路径：

```json
"chrome": {
  "exe": "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "port": 9222,
  "user_data_dir": "C:/path/to/chrome-profile",
  "headless": false
}
```

- `user_data_dir` 建议单独目录，登录一次 DeepSeek 后长期复用
- `headless` 保持 `false`（无头模式会导致模型输出获取失败）

### 3. 运行

```bash
python main.pyw
```

首次运行会自动生成 `config.json` 与 `prompt.json`（均可随时修改）。

### 4. 使用

1. 点击「连接页面」，连上 Chrome 并复用 DeepSeek 聊天页
2. 点击「初始化」，注入系统提示词（让模型知道自己的动作能力）
3. 直接对话即可，模型会调用本地动作完成任务

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `max_action_rounds` | 单次对话最大动作轮数 |
| `auto_max_rounds` | 自动模式最大续接轮数 |
| `action_timeout` / `shell_timeout` | 生成超时 / Shell 超时（秒） |
| `min_send_interval` / `max_send_interval` | 发送间隔下限 / 退避上限（动态限速） |
| `work_dir` | 动作执行与文件读写根目录 |
| `background_image` / `blur_strength` / `font_scale` | 外观 |
| `watch_explorer` / `watch_interval` | 资源管理器监测切换工作区 |

> `config.json`、`prompt.json`、`audit.log`、`chat_logs/` 均为运行时生成，已 gitignore，不进版本库。

## 会话本地化

对话流水以 JSONL 落盘，每个会话一个文件（`chat_logs/<session-id>.jsonl`）：

```json
{"ts": "...", "kind": "user", "session": "...", "text": "..."}
{"ts": "...", "kind": "assistant_text", "session": "...", "text": "..."}
{"ts": "...", "kind": "tool", "session": "...", "type": "shell", "success": true, "duration_ms": 42}
{"ts": "...", "kind": "url", "session": "...", "url": "https://...", "title": "..."}
```

- **追加即落盘**，抗窗口意外关闭
- 工具记录仅存元信息（类型 / 目标 / 成败 / 耗时），不存输出正文
- 界面「历史会话」按钮可列出本地会话，点击一键恢复（Chrome 跳转 + 记录重放）

## 扩展技能

在 `actions/` 下新建一个 `.py`，定义 `META` 与 `run` 即可，无需改内核：

```python
META = {
    "type": "my_skill",
    "icon": "fa-solid fa-star",
    "label": "我的技能",
    "color": "#facc15",
    "order": 120,
    "description": "一句话描述",
    "params": [],
    "accepts_body": False,
    "prompt": "my_skill：说明与示例……\n",   # 编号由内核动态生成，无需写死
}

def run(ctx, params, body):
    return {"success": True, "summary": "完成", "feedback": "结果文本"}
```

重载后自动出现在工具协议中。

## 打包

```bash
pyinstaller --noconfirm --clean deephelp.spec
```

产物：`dist/deephelp.exe`（单文件、不压缩、含图标与版本信息）。

`deephelp.spec` 要点：

- 打入 `webui/`、`actions/`、`favicon.ico` 与 `playwright/driver`
- `hiddenimports` 含 `prompt`（`actions/prompt_edit.py` 动态 import）
- 排除 `config.json` / `prompt.json` / `audit.log` / `chat_logs/`（运行时生成）

## 常见问题

**Q：Markdown 不渲染 / 显示原始文本？**
A：多为 pywebview 内置 HTTP 服务器连接被拒，导致 vendor 库加载失败。已在 `main.pyw` 将 `request_queue_size` 提到 128 修复。

**Q：改了代码没生效？**
A：确认没有多个实例在跑（已加单实例锁）；打包版需重新打包。

**Q：连不上 Chrome？**
A：确认 `config.json` 里 `chrome.exe` 路径正确、`port` 未被占用、`user_data_dir` 可写。

## License

[MIT](LICENSE) © Xiao-no-love

---
---

# English

## Overview

DeepHelp connects a large language model to your local system. You issue instructions in natural language; the model invokes local skills through action tags — reading and writing files, running commands, applying patches, managing background services — and the results are fed back to the model, iterating until the task is done.

Every action runs locally. The model only makes decisions.

## Features

- **Local GUI**: frameless `pywebview` (WebView2) interface, built with pure web tech
- **AI-driven**: `Playwright` connects to Chrome over CDP and drives the DeepSeek web app
- **17 built-in actions**: file I/O, command execution, Python execution, smart patches, service management, session titles, and more
- **Pluggable skills**: each skill in `actions/` is a standalone module — adding one means dropping in a `.py` file, with zero kernel changes
- **Streamed interleaved output**: text and tool cards laid out in the model's original order
- **Auto mode**: automatically continues when the model pauses, until the goal or round cap is reached
- **Message queueing**: type anytime, even while busy; messages merge into the next round
- **Session persistence**: conversation streams are stored as JSONL (`chat_logs/`), with a history list and one-click restore
- **Markdown rendering**: tables, code highlighting, lists and quotes
- **Customizable appearance**: background image, card blur, font scale
- **Single-file distribution**: packaged by PyInstaller as a portable exe

## Architecture

```
┌─────────────┐   JS↔Python   ┌──────────────┐   CDP    ┌──────────┐
│  webui/     │ ◄───────────► │   api.py     │ ◄──────► │  Chrome  │
│ (pywebview) │   evaluate_js │   (bridge)   │          │ DeepSeek │
└─────────────┘               └──────┬───────┘          └──────────┘
                                     │
                              ┌──────┴───────┐
                              │   agent.py   │  Playwright driver
                              │  action.py   │  action parsing & exec
                              └──────┬───────┘
                                     │ dynamic load
                              ┌──────┴───────┐
                              │  actions/*.py │  17 skills
                              └──────────────┘
```

Workflow: **user message → model reply → parse action tags → local execution → feed results back → model continues**, looping until the task is complete.

## Project Structure

```
optimize/
├── main.pyw            # entry (single-instance lock + HTTP server hardening)
├── api.py              # pywebview JS↔Python bridge (task scheduling)
├── agent.py            # DeepSeek browser agent (Playwright)
├── action.py           # action parsing & execution kernel
├── chatlog.py          # conversation stream recorder (JSONL, local)
├── config.py           # default config + system prompt assembly
├── prompt.py           # persona / rules / notes (prompt.json)
├── actions/            # pluggable skills (one .py per skill)
├── webui/              # frontend (vanilla HTML/CSS/JS)
│   ├── demo.html
│   ├── css/            # main.css / body.css
│   ├── js/             # app.js / init.js
│   └── vendor/         # marked / DOMPurify / highlight.js / FontAwesome
├── deephelp.spec       # PyInstaller spec
├── version_info.txt    # exe version info
└── requirements.txt
```

## Built-in Actions

| Action | Description | Key params |
|---|---|---|
| `python` | Execute Python code | `cwd` |
| `shell` | Execute shell commands | `cwd`, `timeout` |
| `file_read` | Read a file | `file`, `max_chars` |
| `file_write` | Write (overwrite) | `file` |
| `file_append` | Append to end | `file` |
| `file_delete` | Delete file/directory | `file` |
| `dir_list` | List a directory | `path` |
| `replace_lines` | Replace by line, multi-segment `@@` supported | `file`, `start`, `end`, `expect` |
| `smart_patch` | unified diff patch (pre-validate → apply → verify + rollback) | `file`, `context` |
| `python_reset` | Reset the Python execution environment | — |
| `auto_mode` | Toggle auto mode | body: `on` / `off` |
| `notice` | Windows system notification | `title`, `msg` |
| `prompt_edit` | Read/write own `prompt.json` | `field`, `mode` |
| `service_list` | List managed background services | — |
| `service_log` | View service logs | `service`, `tail` |
| `service_stop` | Stop a service | `service` |
| `set_chat_title` | Change the DeepSeek session title | `title` |

> Results are returned by default (`replay` defaults to `true`); disable with `replay="false"`.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> `playwright install chromium` is **not** required — the app connects to your system Chrome (debug port) rather than Playwright's bundled browser.

### 2. Prepare Chrome

The app connects to Chrome over the CDP debug port. After the first run, fill in the Chrome path in the generated `config.json`:

```json
"chrome": {
  "exe": "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "port": 9222,
  "user_data_dir": "C:/path/to/chrome-profile",
  "headless": false
}
```

- Use a dedicated `user_data_dir`; log in to DeepSeek once and reuse it
- Keep `headless` `false` (headless mode breaks model output capture)

### 3. Run

```bash
python main.pyw
```

On first run, `config.json` and `prompt.json` are generated automatically.

### 4. Usage

1. Click **Connect** to attach to Chrome and reuse the DeepSeek chat page
2. Click **Initialize** to inject the system prompt (so the model knows its action capabilities)
3. Just chat — the model invokes local actions to complete tasks

## Configuration (config.json)

| Field | Description |
|---|---|
| `max_action_rounds` | Max action rounds per conversation |
| `auto_max_rounds` | Max continuation rounds in auto mode |
| `action_timeout` / `shell_timeout` | Generation timeout / shell timeout (s) |
| `min_send_interval` / `max_send_interval` | Send interval floor / backoff ceiling (dynamic rate limiting) |
| `work_dir` | Root for action execution and file I/O |
| `background_image` / `blur_strength` / `font_scale` | Appearance |
| `watch_explorer` / `watch_interval` | Explorer monitoring to switch workspace |

> `config.json`, `prompt.json`, `audit.log`, and `chat_logs/` are runtime-generated and gitignored.

## Session Persistence

Conversation streams are stored as JSONL, one file per session (`chat_logs/<session-id>.jsonl`):

```json
{"ts": "...", "kind": "user", "session": "...", "text": "..."}
{"ts": "...", "kind": "assistant_text", "session": "...", "text": "..."}
{"ts": "...", "kind": "tool", "session": "...", "type": "shell", "success": true, "duration_ms": 42}
{"ts": "...", "kind": "url", "session": "...", "url": "https://...", "title": "..."}
```

- **Append-on-write**, resilient to unexpected window closure
- Tool records keep metadata only (type / target / success / duration), never output bodies
- The **History** button lists local sessions; one click restores (Chrome navigation + stream replay)

## Extending Skills

Create a `.py` in `actions/` defining `META` and `run`; no kernel changes needed:

```python
META = {
    "type": "my_skill",
    "icon": "fa-solid fa-star",
    "label": "My Skill",
    "color": "#facc15",
    "order": 120,
    "description": "One-line description",
    "params": [],
    "accepts_body": False,
    "prompt": "my_skill: description and examples...\n",   # numbering is auto-generated
}

def run(ctx, params, body):
    return {"success": True, "summary": "done", "feedback": "result text"}
```

It appears in the tool protocol after reload.

## Packaging

```bash
pyinstaller --noconfirm --clean deephelp.spec
```

Output: `dist/deephelp.exe` (single file, uncompressed, with icon and version info).

`deephelp.spec` notes:

- Bundles `webui/`, `actions/`, `favicon.ico`, and `playwright/driver`
- `hiddenimports` includes `prompt` (dynamically imported by `actions/prompt_edit.py`)
- Excludes `config.json` / `prompt.json` / `audit.log` / `chat_logs/` (runtime-generated)

## FAQ

**Q: Markdown doesn't render / shows raw text?**
A: Usually the pywebview built-in HTTP server refusing connections, so vendor libs fail to load. Fixed in `main.pyw` by raising `request_queue_size` to 128.

**Q: Code changes don't take effect?**
A: Check that no multiple instances are running (single-instance lock added); the packaged build requires repackaging.

**Q: Can't connect to Chrome?**
A: Verify the `chrome.exe` path in `config.json`, that `port` is free, and `user_data_dir` is writable.

## License

[MIT](LICENSE) © Xiao-no-love