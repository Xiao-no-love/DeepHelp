
"""技能：file_write — 写入文件（覆盖）"""

import os

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

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
        + "   " + _A + ' type="file_write" id="write1" file="log.txt"' + _RB
        + "\n新的日志内容\n" + _C + "\n"
    ),
}


def _detect_eol(path):
    """探测已存在文件的换行风格；不存在则用 \n（跨平台/git 友好）。"""
    try:
        if not os.path.exists(path):
            return "\n"
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(65536)
        if "\r\n" in sample:
            return "\r\n"
        if "\r" in sample:
            return "\r"
        return "\n"
    except Exception:
        return "\n"


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}
    path = ctx.resolve_path(file_)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    # 统一换行：保持已存在文件的换行风格，避免把 CRLF 项目改成 LF（或反之）
    eol = _detect_eol(path)
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    if eol != "\n":
        text = text.replace("\n", eol)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    n = len(text)
    return {
        "success": True, "summary": "写入 " + str(n) + " 字符",
        "feedback": "文件写入成功: " + path + "\n已写入 " + str(n) + " 字符",
        "info": {"path": path, "char_count": n},
    }
