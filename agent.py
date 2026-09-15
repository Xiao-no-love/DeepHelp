"""
DeepHelp — DeepSeek 浏览器代理
通过 Playwright 操控 Chrome 与 DeepSeek 对话
"""

import os
import socket
import time
import threading
import subprocess
from playwright.sync_api import sync_playwright



from config import SEND_SVG, COPY_SVG, DEFAULT_CONFIG, deep_merge, build_system_prompt

# 串行化"探端口 + 启动 Chrome"，避免预启动线程与连接线程重复拉起 Chrome
_chrome_launch_lock = threading.Lock()
_chrome_launched = False
_chrome_launch_time = 0.0


def ensure_chrome_running(cfg, on_status=None):
    """确保 Chrome 以调试端口运行：探端口 → 没开则拉起进程。
    纯进程层，不涉及 playwright，因此可被后台线程安全地提前预启动。
    返回 True 表示端口已开或已成功拉起进程；False 表示 exe 不存在/启动失败。"""
    def _report(msg):
        if on_status:
            on_status(msg)

    chrome_cfg = cfg["chrome"]
    port = chrome_cfg["port"]

    def _port_open():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            return s.connect_ex(("localhost", port)) == 0
        finally:
            s.close()

    # 加锁串行化"探端口 + 启动"，避免预启动线程与连接线程同时拉起两个 Chrome
    global _chrome_launched, _chrome_launch_time
    with _chrome_launch_lock:
        if _port_open():
            return True
        # 近期已拉起过：给 Chrome 冷启动留时间窗，避免重复 Popen
        if _chrome_launched and (time.time() - _chrome_launch_time) < 20:
            return True

        exe = chrome_cfg["exe"]
        if not os.path.isfile(exe):
            return False
        args = [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={chrome_cfg['user_data_dir']}",
        ]
        if chrome_cfg.get("new_window"):
            args.append("--new-window")
        if chrome_cfg.get("no_first_run"):
            args.append("--no-first-run")
        if chrome_cfg.get("headless"):
            args.append("--headless")
        extra = chrome_cfg.get("extra_args", "").strip()
        if extra:
            args.extend(extra.split())
        _report("正在启动 Chrome...")
        try:
            subprocess.Popen(args)
        except Exception:
            return False
        _chrome_launched = True
        _chrome_launch_time = time.time()
        return True

class DeepSeekAgent:
    """DeepSeek 网页版对话代理"""

    def __init__(self, config):
        self._cfg = config
        self._playwright = None
        self._browser = None
        self._page = None
        self._send_btn = None
        self._textarea = None
        agent_cfg = config.get("agent") or {}
        self._sel = deep_merge(
            DEFAULT_CONFIG["agent"]["selectors"], agent_cfg.get("selectors", {})
        )
        self._tmg = deep_merge(
            DEFAULT_CONFIG["agent"]["timing"], agent_cfg.get("timing", {})
        )
        self._send_svg = agent_cfg.get("send_svg", SEND_SVG)
        self._copy_svg = agent_cfg.get("copy_svg", COPY_SVG)


    def _connect_cdp(self, on_status=None):
        """连接 Chrome 实例（仅 CDP，不处理页面）"""
        chrome_cfg = self._cfg["chrome"]
        port = chrome_cfg["port"]

        def _report(msg):
            if on_status:
                on_status(msg)

        _report("正在搜索已有 Chrome 实例...")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port_open = sock.connect_ex(("localhost", port)) == 0
        sock.close()

        if port_open:
            # 端口已开：直接尝试 CDP 连接（Chrome 可能仍在初始化，重试若干次）
            for _ in range(10):
                try:
                    self._playwright = sync_playwright().start()
                    self._browser = self._playwright.chromium.connect_over_cdp(
                        f"http://localhost:{port}"
                    )
                    _report("已连接到已有 Chrome 实例")
                    return
                except Exception:
                    if self._playwright:
                        try:
                            self._playwright.stop()
                        except Exception:
                            pass
                        self._playwright = None
                    time.sleep(1)
            raise RuntimeError("Chrome 端口已占用但无法通过 CDP 连接")

        if not ensure_chrome_running(self._cfg, _report):
            raise FileNotFoundError(f"Chrome 不存在或无法启动: {chrome_cfg.get('exe')}")
        for _ in range(40):
            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.connect_over_cdp(
                    f"http://localhost:{port}"
                )
                _report("Chrome 已启动并连接")
                return
            except Exception:
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except Exception:
                        pass
                    self._playwright = None
                time.sleep(1)
        raise RuntimeError("无法连接 Chrome（已启动但连接超时）")

    def reconnect(self, on_status=None):
        """重连：优先复用已有聊天页面，否则打开 DeepSeek 首页"""
        self._connect_cdp(on_status)

        def _report(msg):
            if on_status:
                on_status(msg)

        # 查找已有的聊天页面 (URL 以 https://chat.deepseek.com/a/chat/s 开头)
        for ctx in self._browser.contexts:
            for page in ctx.pages:

                if page.url.startswith(self._sel["chat_page_prefix"]):
                    self._page = page
                    _report("已切换到已有聊天页面")
                    break
            if self._page:
                break

        if not self._page:
            _report("正在打开 DeepSeek...")
            if self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[0]
            else:
                self._page = self._browser.contexts[0].new_page()
            self._page.goto(self._cfg["deepseek_url"])
            self._page.wait_for_load_state("networkidle")

        self._page.bring_to_front()


        try:
            self._send_btn = self._locate_send_button()
        except Exception:
            self._send_btn = None


        self._textarea = self._page.locator(self._sel["textarea"]).first

    def _get_svg_path(self, el):
        """获取按钮内 SVG path 的 d 属性"""
        return el.evaluate("el => el.querySelector('svg path')?.getAttribute('d')")

    def _is_sendable(self):
        """发送按钮是否可用"""
        cls = self._send_btn.evaluate("el => el.className")
        return (

            self._sel["disabled_class"] not in cls

            and self._get_svg_path(self._send_btn) == self._send_svg
        )

    def _is_generating(self):
        """是否正在生成回复（按钮图标为停止图标）"""


        return self._get_svg_path(self._send_btn) != self._send_svg

    def _find_button_by_svg(self, svg_path, scope=None, last=False):
        """在 scope（默认整页）内查找匹配指定 SVG 图标 path 的按钮"""
        root = scope if scope is not None else self._page
        btns = root.locator('[role="button"], button')
        count = btns.count()
        found = None
        for i in range(count):
            btn = btns.nth(i)
            try:
                d = btn.evaluate("el => el.querySelector('svg path')?.getAttribute('d')")
            except Exception:
                continue
            if d == svg_path:
                if not last:
                    return btn
                found = btn
        return found



    def _locate_send_button(self):
        """定位发送/停止按钮：用稳定的 class 锚点。
        注意：图标会随状态（发送↔停止）变化，绝不能用图标做定位，否则按钮一变图标
        locator 就落空。图标只用于 _is_sendable / _is_generating 判断状态。"""

        btn = self._page.locator(self._sel["send_button"])
        if btn.count() > 0:
            return btn.first
        # 兜底：按发送图标扫描（仅当主锚点失效时）

        fb = self._find_button_by_svg(self._send_svg)
        if fb is not None:
            return fb

        return self._page.locator(self._sel["send_button_fallback"]).first


    def _locate_copy_button(self):
        """定位最后一条 AI 回复的复制按钮。
        从后往前找含 .ds-markdown 的消息，取其父级中“不在代码块内”的复制按钮，
        避开用户消息复制键、代码块复制键、历史消息复制键。"""

        containers = self._page.locator(self._sel["message_container"])
        try:
            cn = containers.count()
        except Exception:
            cn = 0
        for ci in range(cn):
            container = containers.nth(ci)
            try:

                msgs = container.locator(self._sel["message"])
                n = msgs.count()
            except Exception:
                continue
            if n == 0:
                continue
            for i in range(n - 1, -1, -1):
                m = msgs.nth(i)
                try:

                    if m.locator(self._sel["markdown"]).count() == 0:
                        continue
                    parent = m.locator("xpath=..")
                    cps = parent.locator(
                        '[role="button"]:has(svg path[d="%s"]), button:has(svg path[d="%s"])'

                        % (self._copy_svg, self._copy_svg)
                    )
                    cc = cps.count()
                except Exception:
                    continue
                picked = None
                for j in range(cc):
                    cb = cps.nth(j)
                    try:
                        in_code = cb.evaluate(
                            "el => !!(el.closest('pre') || el.closest('[class*=code-block]'))"
                        )
                    except Exception:
                        in_code = True
                    if not in_code:
                        picked = cb
                if picked is not None:
                    return picked
        raise RuntimeError("未能定位复制按钮：未找到非代码块的复制图标")

    def send(self, prompt):
        """
        发送提示词，等待生成完成，获取AI回复文本
        兼容无头模式，不依赖系统剪贴板、不依赖pyperclip
        复用网页原生复制逻辑输出，和手动复制效果完全一致
        """
        timeout_ms = self._cfg["action_timeout"] * 1000

        textarea = self._textarea

        # 每轮发送前刷新发送按钮定位（防止 nth 索引随页面按钮增减而漂移）
        self._send_btn = self._locate_send_button()

        # 注入劫持脚本，仅首次执行会重写API
        self._page.evaluate("""
        if (!window.__orig_exec_cmd) {
            window.__orig_exec_cmd = document.execCommand.bind(document);
            window.__captured_copy_text = null;

            navigator.clipboard.writeText = async function(text) {
                window.__captured_copy_text = text;
            };

            document.execCommand = function(cmd) {
                if (cmd === "copy") {
                    const ta = document.querySelector("textarea");
                    if (ta) window.__captured_copy_text = ta.value;
                }
                return window.__orig_exec_cmd(cmd);
            }
        }
        """)


        # 清空输入框，写入prompt
        textarea.fill("")
        textarea.fill(prompt)

        # 等待发送按钮变为可发送状态

        for _ in range(self._tmg["sendable_retries"]):
            if self._is_sendable():
                break

            time.sleep(self._tmg["sendable_interval"])
        else:
            raise RuntimeError("发送按钮长时间不可用，无法发送请求")

        # 使用回车发送消息
        textarea.press("Enter")

        # 等待进入生成中状态

        for _ in range(self._tmg["generating_retries"]):
            if self._is_generating():
                break

            time.sleep(self._tmg["generating_interval"])
        else:
            raise RuntimeError("发送后未检测到AI进入生成状态")

        # 循环等待生成结束
        start_time = time.time()
        while self._is_generating():
            if (time.time() - start_time) * 1000 > timeout_ms:
                raise TimeoutError(f"AI回复超时，设置超时 {timeout_ms}ms")

            time.sleep(self._tmg["generating_poll"])


        # 定位最后一条消息的复制按钮（按复制图标 SVG path 精确匹配，避免 nth 玄学）
        copy_btn = self._locate_copy_button()

        # 清空上一轮缓存的复制结果
        self._page.evaluate("(()=>{window.__captured_copy_text = null;})()")

        # 触发网页复制按钮
        copy_btn.click()

        # 轮询获取劫持捕获的文本
        poll_start = time.time()
        result = None
        while True:
            # ✅修复：立即执行函数包裹，禁止顶层return语法
            result = self._page.evaluate("(()=>{return window.__captured_copy_text;})()")
            if result is not None:
                break

            if time.time() - poll_start > self._tmg["copy_poll_timeout"]:
                raise RuntimeError("触发复制后未能捕获到文本内容，请检查复制按钮定位")

            time.sleep(self._tmg["copy_poll_interval"])

        return result

    def inject_system_prompt(self):
        """注入系统提示：人设取自 config.json 的 persona（可配），工具协议写死不可改"""
        persona = self._cfg.get("persona")
        reply = self.send(build_system_prompt(persona))
        return reply
        return reply

    def disconnect(self):
        """断开连接，释放 Playwright 资源"""
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._browser = None
        self._page = None

    @property
    def is_connected(self):
        """是否已连接"""
        return self._playwright is not None and self._browser is not None
