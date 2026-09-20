"""技能：service_log — 查看受托管后台服务的日志尾部"""

import os
import sys
import importlib.util

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "service_log",
    "icon": "fa-solid fa-file-lines",
    "label": "服务日志",
    "color": "#a3e635",
    "order": 77,
    "description": "查看托管后台服务的日志尾部（默认最后 50 行）",
    "params": [
        {"name": "service", "required": False, "desc": "服务ID（如 svc001）"},
        {"name": "pid", "required": False, "desc": "进程PID（与 id 二选一）"},
        {"name": "tail", "required": False, "type": "int", "default": 50, "desc": "显示尾部行数"},
    ],
    "accepts_body": False,
    "prompt": (
        "service_log：查看托管服务的日志尾部。参数 id 或 pid 指定服务，tail 指定行数（默认50）。\n"
        "    示例：\n"
        + "   " + _A + ' type="service_log" id="log1" service="svc001" tail="80"' + _RB + _C + "\n"
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
        tail = int(params.get("tail", 50))
    except (ValueError, TypeError):
        tail = 50
    try:
        pm = _load_pm().get_manager()
        content, err = pm.get_log(ident, tail=tail)
    except Exception as e:
        return {"success": False, "summary": "读取失败", "error": str(e),
                "feedback": "读取服务日志失败: " + str(e)}

    if err:
        return {"success": False, "summary": "读取失败", "error": err,
                "feedback": err}
    if not content:
        return {"success": True, "summary": "日志为空",
                "feedback": "服务 " + str(ident) + " 的日志为空（尚无输出）。",
                "info": {"service_id": str(ident), "tail": tail, "content": ""}}
    return {
        "success": True,
        "summary": "日志尾部 " + str(tail) + " 行",
        "feedback": "服务 " + str(ident) + " 日志（尾 " + str(tail) + " 行）：\n" + content,
        "info": {"service_id": str(ident), "tail": tail, "content": content},
    }