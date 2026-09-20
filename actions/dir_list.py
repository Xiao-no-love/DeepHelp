
"""技能：dir_list — 列出目录内容"""

import os

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "dir_list",
    "icon": "fa-solid fa-folder-tree",
    "label": "目录列表",
    "color": "#9ca3af",
    "order": 70,
    "description": "列出目录中的文件和子目录",
    "params": [{"name": "path", "required": False, "desc": "目录路径（默认当前目录）"}],
    "accepts_body": False,
    "prompt": (
        "7. dir_list：列出目录中的文件和子目录。可选参数 path（不填则为当前工作目录）。\n"
        "   示例：\n"
        + "   " + _A + ' type="dir_list" id="list1" path="src"' + _RB + _C + "\n"
    ),
}


def run(ctx, params, body):
    path_arg = params.get("path") or "."
    target = ctx.resolve_path(path_arg)
    if not os.path.isdir(target):
        return {"success": False, "summary": "目录不存在",
                "error": "目录不存在: " + target,
                "feedback": "目录不存在: " + target}

    items = os.listdir(target)
    dirs, files = [], []
    for item in items:
        full = os.path.join(target, item)
        (dirs if os.path.isdir(full) else files).append(item)
    dirs.sort(key=str.lower)
    files.sort(key=str.lower)

    detailed = []
    for d in dirs:
        detailed.append("[DIR]  " + d + "/")
    for fname in files:
        full = os.path.join(target, fname)
        size = os.path.getsize(full)
        detailed.append("[FILE] " + fname + "  " + ctx.format_size(size))
    output = "\n".join(detailed) if detailed else "(空目录)"

    return {
        "success": True,
        "summary": str(len(dirs)) + " 个目录, " + str(len(files)) + " 个文件",
        "feedback": "目录列表 (" + target + "):\n" + output,
        "info": {"path": target, "count": len(items), "dirs": len(dirs),
                 "files": len(files), "output": output},
    }
