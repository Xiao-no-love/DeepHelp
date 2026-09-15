"""
DeepHelp — 具备本地操作能力的 AI 助手
通过 pywebview 提供 GUI，通过 Playwright 操控 DeepSeek 对话
入口文件
"""

import os
import sys
import webview
from api import Api
from config import WORK_DIR


def main():
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