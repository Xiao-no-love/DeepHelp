
"""技能：file_append — 追加内容到文件末尾"""

import os

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "file_append",
    "icon": "fa-solid fa-file-circle-plus",
    "label": "追加文件",
    "color": "#fb923c",
    "order": 50,
    "description": "追加内容到文件末尾",
    "params": [{"name": "file", "required": True, "desc": "文件路径"}],
    "accepts_body": True,
    "prompt": (
        "5. file_append：追加内容到文件末尾。必需参数 file，body内为追加内容。\n"
        "   示例：\n"
        + "   " + _A + ' type="file_append" id="append1" file="log.txt"' + _GT
        + "\n追加这一行\n" + _C + "\n"
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

    # 自动补换行：文件已存在、非空、末尾无换行、且追加内容不以换行开头
    prefix = ""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            last = f.read(1)
        if last != b"\n" and not body.startswith("\n"):
            prefix = "\n"

    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + body)

    n = len(body)
    extra = "（已自动补换行）" if prefix else ""
    return {
        "success": True, "summary": "追加 " + str(n) + " 字符" + extra,
        "feedback": "文件追加成功: " + path + "\n已追加 " + str(n) + " 字符" + extra,
        "info": {"path": path, "char_count": n, "added_newline": bool(prefix)},
    }
