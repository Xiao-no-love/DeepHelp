# DeepHelp

> 一个具备**本地操作能力**的 AI 助手 —— 用 pywebview 做界面，用 Playwright 驱动浏览器与 DeepSeek 对话，把自然语言变成真实的文件读写与命令执行。

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Playwright-powered-2EAD33?logo=playwright&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

---

## ✨ 特性

- 🖥️ **本地 GUI**：基于 `pywebview`，无边框界面，Web 技术写 UI
- 🤖 **AI 驱动**：通过 Playwright 控制浏览器操作 DeepSeek 对话
- 🛠️ **本地操作**：读/写/追加/删除文件、执行 Python 与 Shell、智能补丁
- 🧩 **可扩展动作**：`actions/` 下每个动作独立成模块，易于新增
- ⚡ **流式响应**：实时展示 AI 的每一步操作与结果

## 🏗️ 项目结构

```
optimize/
├── main.pyw            # 入口
├── api.py              # 前后端桥接 API
├── agent.py            # Agent 核心逻辑
├── action.py           # 动作调度
├── config.py           # 配置
├── prompt.py           # Prompt 构建
├── actions/            # 可执行的本地动作
│   ├── file_read.py
│   ├── file_write.py
│   ├── replace_lines.py
│   ├── smart_patch.py
│   ├── shell_exec.py
│   └── ...
└── webui/              # 前端界面
    ├── demo.html
    ├── css/
    └── js/
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置

复制示例配置并修改本地路径：

```bash
cp config.example.json config.json
```

### 3. 运行

```bash
python main.pyw
```

## 📦 打包（可选）

使用 PyInstaller 打包为单文件 exe：

```bash
pyinstaller --noconsole --add-data "webui;webui" main.pyw
```

> 注意：Playwright 需要额外把 `playwright/driver` 一并打包。

## 📄 License

[MIT](LICENSE) © Xiao-no-love