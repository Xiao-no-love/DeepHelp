"""技能：service_stop — 停止受托管的后台服务（含子进程树）"""

import os
import sys
import importlib.util

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "service_stop",
    "icon": "fa-solid fa-power-off",
    "label": "停止服务",
    "color": "#f87171",
    "order": 76,
    "description": "按 服务ID 或 PID 停止托管的后台服务（连同子进程树一起结束）",
    "params": [
        {"name": "service", "required": False, "desc": "服务ID（如 svc001）"},
        {"name": "pid", "required": False, "desc": "进程PID（与 id 二选一）"},
    ],
    "accepts_body": False,
    "prompt": (
        "service_stop：停止一个托管的后台服务（连同子进程树）。参数 id 或 pid 二选一。\n"
        "    示例：\n"
        + "   " + _A + ' type="service_stop" id="stop1" service="svc001"' + _RB + _C + "\n"
    ),
}


def _load_pm():
    if "_process_manager" in sys.modules:
        return sys.modules["_process_manager"]
    try:
        return importlib.import_module("_process_manager")
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "_process_manager", os.path.join(here, "_process_manager.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_process_manager"] = mod
    spec.loader.exec_module(mod)
    return mod


def run(ctx, params, body):
    ident = params.get("service") or params.get("pid")
    if not ident:
        return {"success": False, "summary": "缺少参数", "error": "缺少 id 或 pid",
                "feedback": "请提供 id（服务ID）或 pid 参数。"}
    try:
        pm = _load_pm().get_manager()
        mp = pm.get(ident)
        if mp is None:
            return {"success": False, "summary": "未找到服务", "error": "未找到: " + str(ident),
                    "feedback": "未找到托管服务: " + str(ident)}
        name = mp.name
        pid = mp.pid
        ok, msg = pm.stop(ident)
    except Exception as e:
        return {"success": False, "summary": "停止失败", "error": str(e),
                "feedback": "停止服务失败: " + str(e)}

    return {
        "success": ok,
        "summary": ("已停止 " + str(ident) + " (pid " + str(pid) + ")") if ok else "停止失败",
        "error": None if ok else msg,
        "feedback": ("服务已停止：" + str(ident) + " [" + name + "] pid=" + str(pid) + "\n" + msg)
                    if ok else ("停止失败: " + msg),
        "info": {"service_id": str(ident), "pid": pid, "name": name, "result": msg},
    }