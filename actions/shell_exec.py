
"""技能：shell — 执行 shell 命令"""

import os
import subprocess

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "shell",
    "icon": "fa-solid fa-terminal",
    "label": "Shell",
    "color": "#fbbf24",
    "order": 20,
    "description": "执行 shell 命令",
    "params": [
        {"name": "cwd", "required": False, "desc": "工作目录"},
        {"name": "timeout", "required": False, "type": "int", "default": 30, "desc": "超时秒数"},
    ],
    "accepts_body": True,
    "prompt": (
        "2. shell：执行shell命令。支持可选参数 cwd 指定工作目录，timeout 指定超时秒数。\n"
        "   示例：\n"
        + "   " + _A + ' type="shell" id="shell1" cwd="C:\\项目" timeout="60"' + _GT
        + "\ndir\n" + _C + "\n"
    ),
}


def run(ctx, params, body):
    timeout = ctx.shell_timeout
    try:
        timeout = int(params.get("timeout", timeout))
    except (ValueError, TypeError):
        pass

    cwd = params.get("cwd")
    cwd = ctx.resolve_path(cwd) if cwd else os.getcwd()

    cmd = body.strip()
    if not cmd:
        return {"success": False, "summary": "命令为空", "error": "命令为空",
                "feedback": "shell 命令为空"}

    is_windows = os.name == "nt"
    if is_windows and "\n" in cmd:
        lines = [ln.strip() for ln in cmd.splitlines() if ln.strip()]
        cmd = " & ".join(lines)

    env = os.environ.copy()
    if is_windows:
        env["PATH"] = r"C:\Windows\System32;C:\Windows;" + env.get("PATH", "")

    proc = subprocess.run(
        cmd, shell=True, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
    )
    raw = proc.stdout if proc.stdout is not None else b""
    out = ""
    for enc in ("utf-8", "gbk"):
        try:
            out = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        out = raw.decode("utf-8", errors="replace")

    ok = proc.returncode == 0
    summary = "返回码 " + str(proc.returncode) + ("" if out else " (无输出)")
    return {
        "success": ok, "summary": summary,
        "error": out[:500] if not ok else None,
        "feedback": "Shell 执行完成 (返回码 " + str(proc.returncode) + ")\n输出:\n" + (out or "(无)"),
        "info": {"command": cmd[:200], "output": out},
    }
