
"""技能：file_write — 写入文件（覆盖）"""

import os

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "file_write",
    "icon": "fa-solid fa-pen-to-square",
    "label": "写入文件",
    "color": "#f97316",
    "order": 40,
    "description": "写入文件（覆盖原有内容）",
    "params": [{"name": "file", "required": True, "desc": "文件路径"}],
    "accepts_body": True,
    "prompt": (
        "4. file_write：写入文件（覆盖原有内容）。必需参数 file，body内为要写入的完整内容。\n"
        "   示例：\n"
        + "   " + _A + ' type="file_write" id="write1" file="log.txt"' + _GT
        + "\n新的日志内容\n" + _C + "\n"
    ),
}


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}
    path = ctx.resolve_path(file_)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    n = len(body)
    return {
        "success": True, "summary": "写入 " + str(n) + " 字符",
        "feedback": "文件写入成功: " + path + "\n已写入 " + str(n) + " 字符",
        "info": {"path": path, "char_count": n},
    }
