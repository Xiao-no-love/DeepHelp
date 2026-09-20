"""技能：service_list — 列出受托管的后台服务"""

import os
import sys
import importlib.util

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "service_list",
    "icon": "fa-solid fa-server",
    "label": "服务列表",
    "color": "#38bdf8",
    "order": 75,
    "description": "列出 DeepHelp 托管的所有后台服务（含 pid/状态/运行时长）",
    "params": [],
    "accepts_body": False,
    "prompt": (
        "service_list：列出所有受托管的后台服务（pid、存活状态、运行时长、日志路径）。\n"
        "    用于查看 shell background=\"true\" 启动的服务。示例：\n"
        + "   " + _A + ' type="service_list" id="svc1"' + _RB + _C + "\n"
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


def _fmt_uptime(sec):
    sec = int(sec)
    if sec < 60:
        return str(sec) + "s"
    if sec < 3600:
        return str(sec // 60) + "m" + str(sec % 60) + "s"
    return str(sec // 3600) + "h" + str((sec % 3600) // 60) + "m"


def run(ctx, params, body):
    try:
        pm = _load_pm().get_manager()
        items = pm.list()
    except Exception as e:
        return {"success": False, "summary": "获取服务列表失败", "error": str(e),
                "feedback": "获取服务列表失败: " + str(e)}

    if not items:
        return {"success": True, "summary": "无后台服务",
                "feedback": "当前没有受托管的后台服务。",
                "info": {"services": [], "count": 0}}

    lines = []
    for it in items:
        mark = "● 运行中" if it["alive"] else "○ 已退出"
        lines.append(
            "[" + it["id"] + "] " + mark + "  pid=" + str(it["pid"]) +
            "  运行" + _fmt_uptime(it["uptime_sec"]) + "\n"
            "    名称: " + str(it["name"]) + "\n"
            "    命令: " + it["cmd"][:120] + "\n"
            "    日志: " + it["log_path"]
        )
    alive_n = sum(1 for it in items if it["alive"])
    return {
        "success": True,
        "summary": str(len(items)) + " 个服务（" + str(alive_n) + " 运行中）",
        "feedback": "后台服务列表（共 " + str(len(items)) + " 个）：\n\n" + "\n\n".join(lines),
        "info": {"services": items, "count": len(items), "alive": alive_n},
    }