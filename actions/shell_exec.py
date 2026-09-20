"""技能：shell — 执行 shell 命令

支持两种模式：
- 前台（默认 background=false）：等待命令结束并返回输出，适合短命令。
- 后台（background=true）：用 ProcessManager 托管启动，输出落日志文件，
  立即返回服务 id/pid，绝不留管道句柄给父进程（根治常驻进程导致的阻塞）。
"""

import os
import sys
import importlib.util
import subprocess

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "shell",
    "icon": "fa-solid fa-terminal",
    "label": "Shell",
    "color": "#fbbf24",
    "order": 20,
    "description": "执行 shell 命令（短命令前台执行；长驻服务用 background=true 托管）",
    "params": [
        {"name": "cwd", "required": False, "desc": "工作目录"},
        {"name": "timeout", "required": False, "type": "int", "default": 30, "desc": "超时秒数（仅前台模式）"},
        {"name": "background", "required": False, "type": "bool", "default": False,
         "desc": "true=后台托管启动（适合服务器/长驻进程），立即返回服务 id/pid"},
        {"name": "name", "required": False, "desc": "后台服务的显示名（可选）"},
    ],
    "accepts_body": True,
    "prompt": (
        "2. shell：执行shell命令。支持可选参数 cwd 指定工作目录，timeout 指定超时秒数。\n"
        "   长驻服务（如 node 服务器）请加 background=\"true\"，会托管启动并立即返回服务 id/pid，\n"
        "   之后可用 service_list 查看、service_stop 停止、service_log 看日志。\n"
        "   示例（前台）：\n"
        + "   " + _A + ' type="shell" id="shell1" cwd="C:\\项目" timeout="60"' + _RB
        + "\ndir\n" + _C + "\n"
        + "   示例（后台服务）：\n"
        + "   " + _A + ' type="shell" id="shell2" background="true" name="音乐电台"' + _RB
        + "\nnode index.js\n" + _C + "\n"
    ),
}


def _load_pm():
    """加载 _process_manager（优先 sys.modules，其次按文件路径加载并注册）。"""
    if "_process_manager" in sys.modules:
        return sys.modules["_process_manager"]
    try:
        return importlib.import_module("_process_manager")
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "_process_manager.py")
    spec = importlib.util.spec_from_file_location("_process_manager", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_process_manager"] = mod
    spec.loader.exec_module(mod)
    return mod


def _is_true(v):
    return str(v).lower() in ("true", "1", "yes", "on")


def _norm_cmd(cmd, is_windows):
    """Windows 下把多行命令用 & 串起来（沿用原行为）。"""
    if is_windows and "\n" in cmd:
        lines = [ln.strip() for ln in cmd.splitlines() if ln.strip()]
        cmd = " & ".join(lines)
    return cmd


def _build_env():
    env = os.environ.copy()
    if os.name == "nt":
        env["PATH"] = r"C:\Windows\System32;C:\Windows;" + env.get("PATH", "")
    return env


def _run_background(ctx, params, cmd):
    """后台托管启动。"""
    cwd = params.get("cwd")
    cwd = ctx.resolve_path(cwd) if cwd else os.getcwd()
    name = params.get("name") or None
    try:
        pm = _load_pm().get_manager()
        mp = pm.launch(cmd, cwd=cwd, name=name)
    except Exception as e:
        return {"success": False, "summary": "后台启动失败", "error": str(e),
                "feedback": "后台启动失败: " + str(e)}
    return {
        "success": True,
        "summary": "后台服务已启动 [" + mp.id + "] pid=" + str(mp.pid),
        "feedback": (
            "后台服务已托管启动\n"
            "  服务ID: " + mp.id + "\n"
            "  PID: " + str(mp.pid) + "\n"
            "  命令: " + cmd + "\n"
            "  日志: " + mp.log_path + "\n"
            "  可用 service_list 查看 / service_stop 停止 / service_log 看日志"
        ),
        "info": {"service_id": mp.id, "pid": mp.pid, "name": mp.name,
                 "log_path": mp.log_path, "background": True, "command": cmd[:200]},
    }


def run(ctx, params, body):
    cmd = body.strip()
    if not cmd:
        return {"success": False, "summary": "命令为空", "error": "命令为空",
                "feedback": "shell 命令为空"}

    is_windows = os.name == "nt"
    cmd = _norm_cmd(cmd, is_windows)

    # ── 后台托管模式 ──
    if _is_true(params.get("background", "")):
        return _run_background(ctx, params, cmd)

    # ── 前台模式（原行为，新增异常兜底）──
    timeout = ctx.shell_timeout
    try:
        timeout = int(params.get("timeout", timeout))
    except (ValueError, TypeError):
        pass

    cwd = params.get("cwd")
    cwd = ctx.resolve_path(cwd) if cwd else os.getcwd()
    env = _build_env()

    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd, env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {"success": False, "summary": "执行超时 (" + str(timeout) + "s)",
                "error": "执行超时",
                "feedback": "Shell 执行超时 (" + str(timeout) + "s)，已放弃等待。\n"
                            "提示：长驻服务请改用 background=\"true\"。"}
    except Exception as e:
        return {"success": False, "summary": "执行异常", "error": str(e),
                "feedback": "Shell 执行异常: " + str(e)}

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