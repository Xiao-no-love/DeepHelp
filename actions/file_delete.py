
"""技能：file_delete — 删除指定文件或目录"""

import os
import shutil

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "file_delete",
    "icon": "fa-solid fa-trash-can",
    "label": "删除文件",
    "color": "#f87171",
    "order": 60,
    "description": "删除指定文件或目录",
    "params": [{"name": "file", "required": True, "desc": "文件或目录路径"}],
    "accepts_body": False,
    "prompt": (
        "6. file_delete：删除指定文件或目录。必需参数 file。\n"
        "   示例：\n"
        + "   " + _A + ' type="file_delete" id="delete1" file="temp.txt"' + _RB + _C + "\n"
    ),
}


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}
    path = ctx.resolve_path(file_)
    if not os.path.exists(path):
        return {"success": False, "summary": "文件不存在",
                "error": "文件不存在: " + path,
                "feedback": "文件不存在，无法删除: " + path}
    if os.path.isdir(path):
        shutil.rmtree(path)
        return {"success": True, "summary": "已删除目录",
                "feedback": "目录已删除: " + path, "info": {"path": path}}
    os.remove(path)
    return {"success": True, "summary": "已删除",
            "feedback": "文件已删除: " + path, "info": {"path": path}}
