"""
DeepHelp — WebView API 桥接层
pywebview JS↔Python 通信，窗口控制与对话任务调度
"""

import base64
import json
import os
import queue
import subprocess
import ctypes
try:
    import win32com.client  # noqa: F401  Explorer 监测依赖；静态 import 供 PyInstaller 收集，缺失时不崩
    _HAS_WIN32COM = True
except Exception:
    _HAS_WIN32COM = False
import threading
import time
import tkinter
import tkinter.filedialog
import webview
from webview.dom import DOMEventHandler

from config import DEFAULT_CONFIG, WORK_DIR, CONFIG_FILE, deep_merge
from action import parse_actions, strip_actions, execute_action, get_param_bool
from agent import DeepSeekAgent, ensure_chrome_running


class Api:
    """pywebview JS↔Python 桥接。
    所有后台操作通过单一工作线程串行执行，
    避免多个 daemon 线程竞争 evaluate_js 导致 "cannot switch thread" 异常。
    """

    def __init__(self):
        self._config = self._load_config()
        self._agent = None
        self._maximized = False
        self._busy = False
        self._initialized = False
        self._status_state = "disconnected"   # connecting / connected / error / disconnected
        self._status_msg = ""                 # 覆盖显示的文案（空则用状态默认文案）
        self._pending = []                    # 忙时排队的用户消息，下一轮带出
        self._auto_mode = False               # 自动模式开关
        self._auto_round = 0                  # 自动续接已用轮数
        self._task_queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        # 预启动 Chrome：与窗口创建 / 前端加载并行，缩短"连接中"等待
        self._prelaunch_chrome()
        # Explorer 监测状态
        self._rejected_dirs = set()
        self._last_explorer = set()
        self._watcher = None
        self._watch_stop = threading.Event()

    def _worker_loop(self):
        while True:
            task = self._task_queue.get()
            if task is None:
                break
            try:
                task()
            except Exception:
                pass

    def _post(self, task):
        self._task_queue.put(task)
    def _prelaunch_chrome(self):
        """后台预启动 Chrome：与窗口创建/前端加载并行，缩短"连接中"等待。
        纯进程层操作，不触碰 webview，故可安全地在独立线程执行。"""
        def _run():
            try:
                ensure_chrome_running(self._config)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()
    def _js(self, code):
        try:
            webview.windows[0].evaluate_js(code)
        except Exception:
            pass

    # ── 配置持久化 ──
    @staticmethod
    def _to_data_url(path):
        """将本地图片路径转换为 base64 data URL，文件不存在返回空字符串"""
        if not path or not os.path.isfile(path):
            return ""
        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            mime_map = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            return f"data:{mime};base64,{data}"
        except Exception:
            return ""


    def _load_config(self):
        """从 config.json 加载配置，与 DEFAULT_CONFIG 递归合并（缺失字段自动补默认）。
        首次运行（文件不存在）时落盘一份默认配置，方便用户查看/修改。"""
        if not os.path.exists(CONFIG_FILE):
            cfg = deep_merge(DEFAULT_CONFIG, {})
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return cfg
        saved = {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}
        return deep_merge(DEFAULT_CONFIG, saved)

    def _save_config(self):
        """将当前配置写入 config.json"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    def _make_status(self):
        """组装完整状态对象。state 决定指示灯与默认文案，msg 为可选的覆盖文案，
        page_url 取自 agent 当前页面。"""
        page_url = ""
        try:
            if self._agent is not None:
                page_url = self._agent.page_url
        except Exception:
            page_url = ""
        return json.dumps(
            {
                "state": self._status_state,
                "msg": self._status_msg,
                "port": self._config["chrome"]["port"],
                "page_url": page_url,
                "cwd": os.path.basename(self._config.get("work_dir", WORK_DIR)),
                "cwd_full": self._config.get("work_dir", WORK_DIR),
                "auto_mode": self._auto_mode,
                "auto_round": self._auto_round,
                "auto_max": self._auto_max_rounds(),
            }
        )
    def _set_status(self, state=None, msg=None):
        """更新连接状态并推送到前端。
        state 为 None 时保持当前状态，仅更新 msg（用于进度提示，如"限速等待"）；
        切换 state 且未显式给 msg 时，自动清掉进度覆盖文案。"""
        if state is not None:
            self._status_state = state
            if msg is None:
                self._status_msg = ""
        if msg is not None:
            self._status_msg = msg
        self._js("setStatus(" + self._make_status() + ")")

    # ── 窗口控制 ──
    def minimize_window(self):
        webview.windows[0].minimize()

    def toggle_maximize(self):
        if self._maximized:
            webview.windows[0].restore()
        else:
            webview.windows[0].maximize()
        self._maximized = not self._maximized
        icon = "fa-window-restore" if self._maximized else "fa-window-maximize"
        webview.windows[0].evaluate_js(
            f'document.querySelector("#btn-max i").className = "fa-solid {icon}"'
        )

    def close_window(self):
        self._task_queue.put(None)
        if self._agent:
            self._agent.disconnect()
        webview.windows[0].destroy()

    # ── 启动 ──
    # ── 启动 ──
    def startup(self):
        cfg = dict(self._config)
        bg = cfg.get("background_image", "")
        # base64 只用于前端显示，绝不写回 background_image（否则 config.json 被撑到数 MB）
        cfg["background_data_url"] = self._to_data_url(bg)
        self._js(f"loadSettings({json.dumps(cfg, ensure_ascii=False)})")
        self._setup_drag_drop()
        self._post(self._auto_connect)
        self._start_watcher()

    # ── Explorer 监测 ──
    def _start_watcher(self):
        if not _HAS_WIN32COM:
            return
        if not self._config.get("watch_explorer", True):
            return
        if self._watcher and self._watcher.is_alive():
            return
        self._watch_stop.clear()
        self._watcher = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher.start()

    @staticmethod
    def _explorer_paths():
        """枚举已打开的 Windows 资源管理器窗口，返回本地路径集合"""
        paths = set()
        if not _HAS_WIN32COM:
            return paths
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            wins = shell.Windows()
            for i in range(wins.Count):
                try:
                    w = wins.Item(i)
                    url = w.LocationURL or ""
                    if url.startswith("file:///"):
                        p = url[8:].replace("/", "\\")
                        if p:
                            paths.add(os.path.normpath(p))
                except Exception:
                    continue
        except Exception:
            pass
        return paths

    def _watch_loop(self):
        while not self._watch_stop.is_set():
            try:
                interval = max(1, int(self._config.get("watch_interval", 2)))
            except Exception:
                interval = 2
            self._watch_stop.wait(interval)
            if self._watch_stop.is_set():
                break
            try:
                current = self._explorer_paths()
            except Exception:
                continue
            new = current - self._last_explorer
            self._last_explorer = current
            work = os.path.normpath(self._config.get("work_dir") or WORK_DIR)
            for p in new:
                if p in self._rejected_dirs:
                    continue
                if os.path.normpath(p) == work:
                    continue
                if not os.path.isdir(p):
                    continue
                self._post(lambda path=p: self._js(
                    "showWorkdirSuggestion(" + json.dumps(path.replace("\\", "/"), ensure_ascii=False) + ")"))

    def _setup_drag_drop(self):
        """只注册 drop 桥接（路径只能经 pywebview 原生层拿到）。
        注意：dragenter/dragover 不注册桥接——高频事件走 Python 往返会导致拖拽卡顿，
        改由前端 JS 的 preventDefault 处理，既阻止 WebView2 打开文件，又不阻塞 drop 桥接。"""
        try:
            doc = webview.windows[0].dom.document
            doc.events.drop += DOMEventHandler(
                self._on_file_drop, prevent_default=True
            )
        except Exception as e:
            self._js("showToast(" + json.dumps("拖放注册失败: " + str(e)) + ")")

    def _on_file_drop(self, event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            self._post(lambda: self._show_drop_confirm(paths))

    def _show_drop_confirm(self, paths):
        try:
            webview.windows[0].show()
        except Exception:
            pass
        self._js("showDropConfirm(" + json.dumps(paths, ensure_ascii=False) + ")")

    def _auto_connect(self):
        self._post(lambda: self._do_connect("连接"))

    def _do_connect(self, action_name="连接"):
        """统一的连接逻辑：先断旧连接，再智能复用聊天页面"""
        if self._agent:
            try:
                self._agent.disconnect()
            except Exception:
                pass
            self._agent = None
            time.sleep(0.5)
        try:
            self._set_status("connecting", "连接中...")
            self._agent = DeepSeekAgent(
                self._config, on_status=lambda msg: self._set_status(msg=msg)
            )
            self._agent.reconnect(on_status=lambda msg: self._set_status(msg=msg))
            self._initialized = False
            self._set_status("connecting", "正在加载 DeepSeek...")
            self._set_status("connected")
            self._js('showToast("已连接到 Chrome")')
        except Exception as e:
            self._agent = None
            self._set_status("error", str(e))
            self._js(f"showToast('{action_name}失败: {e}')")

    # ── 重连 ──
    def connect_page(self):
        """手动重连：断开旧连接，智能复用已有聊天页面"""
        self._initialized = False
        self._js("setAgentInitialized(false)")
        self._post(lambda: self._do_connect("重连"))

    # ── 对话 ──
    def initialize_agent(self):
        """手动注入系统提示词，由用户点击按钮触发"""
        if self._agent is None or not self._agent.is_connected:
            self._js('showToast("请先连接到 Chrome")')
            return
        self._post(lambda: self._do_initialize())

    def _do_initialize(self):
        try:
            self._js("setBusy(true)")
            self._agent.inject_system_prompt()
            self._initialized = True
            self._js("setAgentInitialized(true)")
            self._js('showToast("系统提示词已注入")')
        except Exception as e:
            self._js(f"showToast('初始化失败: {e}')")
        finally:
            self._js("setBusy(false)")
            if self._agent is not None and self._agent.is_connected:
                self._set_status("connected")

    # ── 消息构造：统一用块标记，一条消息可含多块 ──
    @staticmethod
    def _build_message(blocks):
        """blocks: [(标题, 内容), ...]，拼成多块消息。标题如 用户消息/工具输出/系统提示。"""
        parts = []
        for title, body in blocks:
            if body is None or str(body).strip() == "":
                continue
            parts.append("[" + title + "]\n" + str(body).rstrip())
        return "\n\n".join(parts)

    def _drain_pending(self):
        """取出并清空排队消息，返回合并后的 [用户消息] 块文本（无则 None）"""
        if not self._pending:
            return None
        msgs = self._pending
        self._pending = []
        self._js("clearQueuedBadge()")
        return self._build_message([("用户消息", "\n\n".join(msgs))])

    def send_message(self, text):
        """任何时刻都接受消息：空闲则立即执行；忙则入队，等下一轮带出。"""
        if not text or not text.strip():
            return
        if self._busy:
            self._pending.append(text)
            self._js("markQueued(" + json.dumps(text, ensure_ascii=False) + ")")
            return
        self._busy = True
        self._post(lambda: self._run_agent(text))

    # ── 自动模式控制（供 AI 的 auto_mode action / 前端按钮调用）──
    def _auto_max_rounds(self):
        try:
            return max(1, int(self._config.get("auto_max_rounds") or 5))
        except (TypeError, ValueError):
            return 5

    def _set_auto_mode(self, on):
        self._auto_mode = bool(on)
        if not self._auto_mode:
            self._auto_round = 0
        self._js("setAutoMode(" + json.dumps({"on": self._auto_mode,
                                              "round": self._auto_round,
                                              "max": self._auto_max_rounds()}) + ")")

    def set_auto_mode_ui(self, on):
        """前端按钮调用：手动开/关自动模式"""
        self._set_auto_mode(on)
        self._js('showToast("自动模式已' + ("开启" if on else "关闭") + '")')

    def pause_auto_mode(self):
        """前端按钮：手动暂停自动模式（不打断当前任务）"""
        self._set_auto_mode(False)
        self._js('showToast("自动模式已暂停")')

    def reset_auto_round(self):
        """前端按钮：轮数清零（自动模式保持，不打断任务）"""
        self._auto_round = 0
        self._set_auto_mode(self._auto_mode)
        self._js('showToast("自动轮数已清零")')

    def _run_agent(self, user_text):
        try:
            self._js("setBusy(true)")
            if self._agent is None or not self._agent.is_connected:
                self._set_status("connecting", "连接中...")
                self._agent = DeepSeekAgent(
                    self._config, on_status=lambda msg: self._set_status(msg=msg)
                )
                self._agent.reconnect(on_status=lambda msg: self._set_status(msg=msg))
                self._initialized = False
                self._set_status("connecting", "正在加载 DeepSeek...")
                self._set_status("connected")

            # 首轮：用户消息（可能叠加排队消息，这里首轮只有本条）
            reply = self._agent.send(self._build_message([("用户消息", user_text)]))

            while True:
                # 内层：动作链
                while True:
                    actions = parse_actions(reply)
                    if not actions:
                        break
                    clean = strip_actions(reply)
                    if clean:
                        self._js(
                            f"addMessage('assistant', {json.dumps(clean, ensure_ascii=False)})"
                        )
                    feedbacks = []
                    auto_cmds = []
                    for type_, id_, params, body in actions:
                        # auto_mode 是控制流级动作，运行时拦截，不走普通执行器
                        if type_ == "auto_mode":
                            cmd = (body or params or "").strip().lower()
                            auto_cmds.append(cmd)
                            self._js("addAction(" + json.dumps({
                                "type": "auto_mode", "id": id_,
                                "icon": "fa-solid fa-robot", "label": "自动模式",
                                "color": "#22d3ee", "success": True,
                                "summary": "自动模式 " + (cmd or "on"),
                                "duration_ms": 0,
                            }, ensure_ascii=False) + ")")
                            continue
                        ok, fb_text, info = execute_action(
                            type_, id_, params, body,
                            shell_timeout=self._config["shell_timeout"],
                            work_dir=self._config.get("work_dir"),
                            action_meta=self._config.get("action_meta"),
                        )
                        self._js("addAction(" + json.dumps(info, ensure_ascii=False) + ")")
                        self._js("addHistory(" + json.dumps(info, ensure_ascii=False) + ")")
                        if get_param_bool(params, "replay", True):
                            feedbacks.append(fb_text)
                    # 应用 auto_mode 指令（off 优先于 on）
                    if "off" in auto_cmds:
                        self._set_auto_mode(False)
                    elif "on" in auto_cmds:
                        self._set_auto_mode(True)
                    if not feedbacks:
                        reply = ""
                        break
                    reply = self._agent.send(self._build_message([("工具输出", "\n\n".join(feedbacks))]))
                if reply:
                    self._js(
                        f"addMessage('assistant', {json.dumps(reply, ensure_ascii=False)})"
                    )

                # 外层：决定是否继续下一轮
                blocks = []
                # 1) 排队消息优先
                pending = self._drain_pending()
                if pending:
                    blocks.append(("用户消息", pending))
                # 2) 自动模式续接
                if self._auto_mode:
                    cap = self._auto_max_rounds()
                    if self._auto_round >= cap:
                        # 超上限：提醒 + 自动关
                        self._js('showToast("自动模式已达上限 ' + str(cap) + ' 轮，已暂停")')
                        self._js("addMessage('assistant', " + json.dumps(
                            "⚠️ 自动模式已达 " + str(cap) + " 轮上限，已自动暂停。需要继续请手动开启。",
                            ensure_ascii=False) + ")")
                        self._set_auto_mode(False)
                    else:
                        self._auto_round += 1
                        self._set_auto_mode(True)   # 刷新前端轮数显示
                        blocks.append(("系统提示",
                            "自动模式：继续推进当前任务（第 " + str(self._auto_round) + "/" + str(cap) + " 轮）。\n"
                            "完成目标后请调用 auto_mode off 关闭自动模式。\n"
                            "若需要用户决策或确认，请用 quiz 出题并先调用 auto_mode off。"))
                if not blocks:
                    break
                reply = self._agent.send(self._build_message(blocks))
                if not reply:
                    break
        except Exception as e:
            self._js(
                f"addMessage('assistant', {json.dumps(f'❌ 错误: {e}', ensure_ascii=False)})"
            )
            if self._agent:
                try:
                    self._agent.disconnect()
                except Exception:
                    pass
                self._agent = None
            self._initialized = False
            self._set_status("error")
            self._js("setAgentInitialized(false)")
        finally:
            self._busy = False
            self._set_auto_mode(False)
            self._js("setBusy(false)")
            if self._agent is not None and self._agent.is_connected:
                self._set_status("connected")
            else:
                self._set_status("disconnected")

    # ── 设置 ──

    def _reset_config(self):
        self._config = deep_merge(DEFAULT_CONFIG, {})


    def save_settings(self, cfg):
        # 前端只回传它管理的字段（chrome/超时/外观等），用 deep_merge 叠加到当前配置，
        # 保护 agent 段（SVG、选择器、时序）等前端不涉及的配置不被整体覆盖抹除。
        self._config = deep_merge(self._config, cfg)
        self._save_config()
        if self._agent:
            self._agent._cfg = self._config
        bg = self._config.get("background_image", "")
        data_url = self._to_data_url(bg)
        self._js("applyBackground(" + json.dumps(data_url or bg) + ")")
        self._js('showToast("设置已保存")')
        # 让"资源管理器监测"开关即时生效
        try:
            if self._watcher and self._watcher.is_alive():
                self._watch_stop.set()
                self._watcher.join(timeout=1)
                self._watcher = None
            self._start_watcher()
        except Exception:
            pass
        # 刷新状态栏（工作区可能变化）
        self._set_status("connected")

    def reset_settings(self):
        self._reset_config()
        self._save_config()
        if self._agent:
            self._agent._cfg = self._config
        cfg = dict(self._config)
        bg = cfg.get("background_image", "")
        cfg["background_data_url"] = self._to_data_url(bg)
        self._js(f"loadSettings({json.dumps(cfg, ensure_ascii=False)})")
        self._js('showToast("已恢复默认设置")')

    def browse_file(self, field_id):
        path = tkinter.filedialog.askopenfilename(title="选择文件")
        if path:
            self._js(f'document.getElementById("{field_id}").value={json.dumps(path)}')

    def browse_folder(self, field_id):
        path = tkinter.filedialog.askdirectory(title="选择目录")
        if path:
            self._js(f'document.getElementById("{field_id}").value={json.dumps(path)}')

    # ── 背景设置 ──
    def browse_background(self, field_id):
        """打开文件对话框选择图片，并立即应用为背景"""
        path = tkinter.filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")],
        )
        if path:
            path = path.replace("\\", "/")
            self._config["background_image"] = path
            self._save_config()
            data_url = self._to_data_url(path)
            self._js(f'document.getElementById("{field_id}").value={json.dumps(path)}')
            self._js("applyBackground(" + json.dumps(data_url or path) + ")")
            self._js('showToast("背景已更新")')

    def set_background(self, path):
        """前端调用设置背景图片（输入框手动输入或移除背景）"""
        if path:
            path = path.replace("\\", "/")
        self._config["background_image"] = path
        self._save_config()
        data_url = self._to_data_url(path) if path else ""
        self._js("applyBackground(" + json.dumps(data_url or path or "") + ")")
        self._js('showToast("背景已更新")')

    # ── 资源管理器（只读）──
    def list_dir(self, path=None):
        """列出目录内容，返回结构化数据供前端资源管理器渲染"""
        target = path or self._config.get("work_dir") or WORK_DIR
        target = os.path.normpath(target)
        if not os.path.isdir(target):
            return {"ok": False, "error": "目录不存在: " + target}
        try:
            entries = []
            for name in os.listdir(target):
                full = os.path.join(target, name)
                try:
                    is_dir = os.path.isdir(full)
                    size = 0 if is_dir else os.path.getsize(full)
                except Exception:
                    is_dir = False
                    size = 0
                entries.append({"name": name, "dir": is_dir, "size": size})
            entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
            parent = os.path.dirname(target)
            return {"ok": True, "path": target,
                    "parent": parent if parent != target else None,
                    "entries": entries}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_file(self, path):
        """只读预览文件内容。二进制/超大文件做拦截。"""
        if not path:
            return {"ok": False, "error": "缺少路径"}
        target = os.path.normpath(path)
        if not os.path.isfile(target):
            return {"ok": False, "error": "文件不存在: " + target}
        try:
            size = os.path.getsize(target)
        except Exception:
            size = 0
        MAX = 512 * 1024  # 512KB 上限
        try:
            with open(target, "rb") as f:
                head = f.read(4096)
            if b"\x00" in head:
                return {"ok": False, "error": "二进制文件，无法预览", "size": size}
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX)
            return {"ok": True, "path": target, "content": content, "size": size,
                    "truncated": size > MAX,
                    "ext": os.path.splitext(target)[1].lower().lstrip(".")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_work_dir(self, path):
        """切换工作区（全局唯一），落盘并刷新状态栏"""
        if not path:
            return {"ok": False, "error": "缺少路径"}
        target = os.path.normpath(path)
        if not os.path.isdir(target):
            return {"ok": False, "error": "目录不存在: " + target}
        self._config["work_dir"] = target
        self._save_config()
        self._set_status("connected")
        return {"ok": True, "path": target}

    def get_work_dir(self):
        """返回当前工作区路径"""
        return {"ok": True, "path": self._config.get("work_dir") or WORK_DIR}

    def open_in_explorer(self, path):
        """在系统资源管理器中打开目录 / 定位文件"""
        target = os.path.normpath(path) if path else (self._config.get("work_dir") or WORK_DIR)
        try:
            if os.path.isfile(target):
                subprocess.Popen(["explorer", "/select,", target])
            elif os.path.isdir(target):
                os.startfile(target)
            else:
                return {"ok": False, "error": "路径不存在: " + target}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    def reject_workdir(self, path):
        """用户拒绝切换，记入内存拒绝名单，本次运行不再提示"""
        if path:
            self._rejected_dirs.add(os.path.normpath(path))
        return {"ok": True}