# DeepHelp

> 一个具备**本地操作能力**的 AI 助手 —— 用 `pywebview` 做界面，用 `Playwright` 驱动浏览器与 DeepSeek 对话，把自然语言变成真实的文件读写与命令执行。

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Playwright-powered-2EAD33?logo=playwright&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/version-0.6.0-blue" />
</p>

---

## ✨ 特性

- 🖥️ **本地 GUI**：基于 `pywebview`（WebView2），无边框界面，纯 Web 技术写 UI
- 🤖 **AI 驱动**：Playwright 通过 CDP 连接 Chrome，操控 DeepSeek 网页版对话
- 🛠️ **13 种本地动作**：文件读写、命令执行、Python 执行、智能补丁、系统通知……
- 🧩 **可插拔技能**：`actions/` 下每个技能独立成模块，新增 = 丢一个 `.py` 文件，内核零改
- ⚡ **流式交错展示**：文字与工具卡片按 AI 原文顺序铺开，所见即所得
- 🔄 **自动模式**：AI 停下时自动续接推进任务，达成目标或达轮数上限自动停
- 📥 **消息排队**：忙碌时仍可随时输入，消息自动并入下一轮，不丢失
- 🎨 **Markdown 渲染**：表格横向滚动、代码高亮、列表/引用/标题完整排版
- 🖼️ **可定制外观**：背景图、卡片模糊度、字号实时调节
- 📦 **单文件分发**：PyInstaller 打包为免安装单 exe

## 🏗️ 架构

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
                              │  actions/*.py │  13 个技能
                              └──────────────┘
```

工作流：**用户消息 → DeepSeek 回复 → 解析动作标签 → 本地执行 → 结果回传 → AI 继续**，循环直到任务完成。

## 📂 项目结构

```
optimize/
├── main.pyw            # 入口（单实例锁 + HTTP 服务器加固）
├── api.py              # pywebview JS↔Python 桥接层（任务调度）
├── agent.py            # DeepSeek 浏览器代理（Playwright 操控）
├── action.py           # 动作解析与执行内核
├── config.py           # 默认配置 + 系统提示组装
├── prompt.py           # 人设/规则/笔记管理（prompt.json）
├── actions/            # 可插拔技能（每个 .py 一个技能）
│   ├── python_exec.py     # Python 代码执行
│   ├── shell_exec.py      # Shell 命令执行
│   ├── file_read.py       # 读文件
│   ├── file_write.py      # 写文件
│   ├── file_append.py     # 追加文件
│   ├── file_delete.py     # 删文件
│   ├── dir_list.py        # 列目录
│   ├── replace_lines.py   # 按行号替换（支持多段）
│   ├── smart_patch.py     # unified diff 智能补丁
│   ├── python_reset.py    # 重置 Python 环境
│   ├── auto_mode.py       # 自动模式开关
│   ├── notice.py          # Windows 系统通知
│   └── prompt_edit.py     # 编辑自身提示词
├── webui/              # 前端界面
│   ├── demo.html
│   ├── css/            # main.css / body.css
│   ├── js/             # app.js / init.js
│   └── vendor/         # marked / DOMPurify / highlight.js / FontAwesome
├── deephelp.spec       # PyInstaller 打包配置
├── version_info.txt    # exe 版本信息
└── requirements.txt
```

## 🛠️ 内置动作

| 动作 | 说明 | 关键参数 |
|---|---|---|
| `python` | 执行 Python 代码 | `cwd` |
| `shell` | 执行 Shell 命令 | `cwd`、`timeout` |
| `file_read` | 读取文件 | `file`、`max_chars` |
| `file_write` | 写入（覆盖） | `file` |
| `file_append` | 追加到末尾 | `file` |
| `file_delete` | 删除文件/目录 | `file` |
| `dir_list` | 列出目录 | `path` |
| `replace_lines` | 按行号替换，**支持多段** `@@` 头 | `file`、`start`、`end`、`expect` |
| `smart_patch` | unified diff 补丁（预校验→应用→校验+回滚） | `file`、`context` |
| `python_reset` | 重置 Python 执行环境 | — |
| `auto_mode` | 开关自动模式 | body: `on`/`off` |
| `notice` | 弹 Windows 系统通知 | `title`、`msg` |
| `prompt_edit` | 读写自身 `prompt.json` | `field`、`mode` |

> 每个动作结果默认回传（`replay` 默认 `true`），可用 `replay="false"` 关闭。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> `playwright install chromium` **非必需** —— 本程序连接的是系统已装的 Chrome（调试端口），不依赖 Playwright 自带浏览器。

### 2. 准备 Chrome

程序通过 **CDP 调试端口** 连接 Chrome。首次运行后在生成的 `config.json` 里填好 Chrome 路径：

```json
"chrome": {
  "exe": "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "port": 9222,
  "user_data_dir": "C:/path/to/chrome-profile",
  "headless": false
}
```

- `user_data_dir` 建议**单独目录**，登录一次 DeepSeek 后长期复用
- `headless` 保持 `false`（无头模式会导致模型输出获取失败）

### 3. 运行

```bash
python main.pyw
```

首次运行会自动生成 `config.json` 与 `prompt.json`（均可随时修改）。

### 4. 使用

1. 点击 **「连接页面」** 连上 Chrome 并复用 DeepSeek 聊天页
2. 点击 **「初始化」** 注入系统提示词（让 AI 知道自己的动作能力）
3. 直接对话即可，AI 会调用本地动作完成任务

## ⚙️ 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `max_action_rounds` | 单次对话最大动作轮数 |
| `auto_max_rounds` | 自动模式最大续接轮数 |
| `action_timeout` / `shell_timeout` | 生成超时 / Shell 超时（秒） |
| `min_send_interval` / `max_send_interval` | 发送间隔下限 / 退避上限（动态限速） |
| `work_dir` | 动作执行与文件读写根目录 |
| `background_image` / `blur_strength` / `font_scale` | 外观 |
| `watch_explorer` / `watch_interval` | 资源管理器监测切换工作区 |

> `config.json`、`prompt.json`、`audit.log` 均为**运行时生成**，已 gitignore，不会进版本库。

## 🧩 扩展技能

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

## 📦 打包

```bash
pyinstaller --noconfirm --clean deephelp.spec
```

产物：`dist/deephelp.exe`（单文件、不压缩、含图标与版本信息）。

`deephelp.spec` 要点：
- 打入 `webui/`、`actions/`、`favicon.ico` 与 `playwright/driver`
- `hiddenimports` 含 `prompt`（`actions/prompt_edit.py` 动态 import）
- 排除 `config.json` / `prompt.json` / `audit.log`（运行时生成）

## ❓ 常见问题

**Q：markdown 不渲染 / 显示原始文本？**
A：多为 pywebview 内置 HTTP 服务器连接被拒导致 vendor 库加载失败。已在 `main.pyw` 将 `request_queue_size` 提到 128 修复。

**Q：改了代码没生效？**
A：确认没有多个实例在跑（已加单实例锁）；打包版需重新打包。

**Q：连不上 Chrome？**
A：确认 `config.json` 里 `chrome.exe` 路径正确、`port` 未被占用、`user_data_dir` 可写。

## 📄 License

[MIT](LICENSE) © Xiao-no-love