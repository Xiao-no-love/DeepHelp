"""
DeepHelp — 具备本地操作能力的 AI 助手
通过 pywebview 提供 GUI，通过 Playwright 操控 DeepSeek 对话
入口文件
"""

import os
import sys
import socketserver

# ── 加固 1：提高内置 HTTP 服务器的连接排队上限 ──
# pywebview 用 wsgiref 的 WSGIServer（基于 socketserver.TCPServer），默认
# request_queue_size=5。前端一次性并发拉取 10+ 个 js/css 资源时，超出 backlog
# 的连接会被拒绝，浏览器报 net::ERR_CONNECTION_REFUSED，导致 marked / DOMPurify
# 等库加载失败、markdown 退化成未渲染的原文。把上限调大以消除该竞态。
# 必须在 import webview 之前设置，确保继承链取到新值。
socketserver.TCPServer.request_queue_size = 128
try:
    import wsgiref.simple_server as _wss
    _wss.WSGIServer.request_queue_size = 128
except Exception:
    pass

import ctypes

# ── 加固 2：单实例锁 ──
# 避免多个 DeepHelp 同时运行：旧实例的 WebView2 仍在时，容易让人误看成"新代码没生效"。
_MUTEX = None


def _acquire_single_instance():
    """用命名互斥体确保只有一个实例。返回 True 表示获得运行权。"""
    global _MUTEX
    try:
        _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "DeepHelp_SingleInstance_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
    except Exception:
        pass
    return True


import webview
from api import Api
from config import WORK_DIR


def main():
    if not _acquire_single_instance():
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "DeepHelp 已在运行。\n请先关闭已有窗口，再启动新的实例。",
                "DeepHelp", 0x40,
            )
        except Exception:
            pass
        return

    if getattr(sys, 'frozen', False):
        html_path = os.path.join(sys._MEIPASS, "webui", "demo.html")
    else:
        html_path = os.path.join(WORK_DIR, "webui", "demo.html")

    api = Api()
    webview.create_window(
        "DeepHelp",
        url=html_path,          # 传本地文件路径，配合 http_server 自动起本地服务
        js_api=api,
        width=1200,
        height=800,
        frameless=True,
        resizable=True,
        easy_drag=False,
        background_color="#000000",
    )
    webview.start(http_server=True, debug=False)


if __name__ == "__main__":
    main()
