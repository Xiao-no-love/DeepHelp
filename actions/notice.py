"""技能：notice — 调用 Windows 系统通知提示用户"""

import os
import html
import tempfile
import subprocess

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

_APPID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"

_PS_TEMPLATE = (
    "$ErrorActionPreference = 'Stop'\n"
    "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]\n"
    "[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]\n"
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
    "$xml.LoadXml(@'\n"
    "{toast}\n"
    "'@)\n"
    "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{appid}').Show($toast)\n"
)

META = {
    "type": "notice",
    "icon": "fa-solid fa-bell",
    "label": "系统通知",
    "color": "#facc15",
    "order": 112,
    "description": "弹出 Windows 桌面通知提示用户（非阻塞，配合自动模式使用）",
    "params": [
        {"name": "title", "required": False, "desc": "通知标题（默认 DeepHelp）"},
        {"name": "msg", "required": False, "desc": "通知正文（也可直接写在 body）"},
    ],
    "accepts_body": True,
    "prompt": (
        "12. notice：弹出 Windows 桌面系统通知，提示老板（非阻塞、无需确认）。\n"
        "    参数：title（可选，标题，默认 DeepHelp）、msg（可选，正文，也可写在 body）。\n"
        "    适用场景：任务完成、需要老板关注、自动模式下的阶段汇报等。\n"
        "    示例：\n"
        "    " + _A + ' type="notice" id="n1" title="任务完成"' + _GT + "已修改 3 个文件，请查看" + _C + "\n"
    ),
}


def _notify(title, msg):
    toast = (
        '<toast><visual><binding template="ToastGeneric">'
        "<text>" + html.escape(title, quote=False) + "</text>"
        "<text>" + html.escape(msg, quote=False) + "</text>"
        "</binding></visual></toast>"
    )
    script = _PS_TEMPLATE.format(toast=toast, appid=_APPID)
    fd, path = tempfile.mkstemp(suffix=".ps1")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write(script)
        # CREATE_NO_WINDOW：避免弹出黑窗口（powershell 默认会带控制台）
        CREATE_NO_WINDOW = 0x08000000
        si = None
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
        except Exception:
            si = None
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=si,
        )
        return r.returncode, (r.stderr or "").strip()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def run(ctx, params, body):
    title = params.get("title") or "DeepHelp"
    msg = params.get("msg") or params.get("message") or (body or "").strip()
    if not msg:
        return {"success": False, "summary": "缺少通知内容",
                "error": "缺少通知内容", "feedback": "缺少通知内容（msg 或 body）"}
    try:
        rc, err = _notify(title, msg)
    except subprocess.TimeoutExpired:
        return {"success": False, "summary": "通知超时", "error": "powershell 超时",
                "feedback": "系统通知超时"}
    except Exception as e:
        return {"success": False, "summary": "通知异常", "error": str(e),
                "feedback": "系统通知异常: " + str(e)}
    if rc != 0:
        return {"success": False, "summary": "通知失败", "error": err[:300],
                "feedback": "系统通知失败: " + err[:200]}
    return {"success": True, "summary": "已发送系统通知: " + msg[:30],
            "feedback": "已发送 Windows 通知 —— " + title + ": " + msg,
            "info": {"title": title, "msg": msg}}