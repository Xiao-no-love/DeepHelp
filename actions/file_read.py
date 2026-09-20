
"""技能：file_read — 读取文件内容"""

import os

_LB = "<"
_RB = ">"
_C = _LB + "/action" + _RB
_A = _LB + "action"

META = {
    "type": "file_read",
    "icon": "fa-solid fa-book-open",
    "label": "读取文件",
    "color": "#34d399",
    "order": 30,
    "description": "读取文件内容",
    "params": [
        {"name": "file", "required": True, "desc": "文件路径"},
        {"name": "max_chars", "required": False, "type": "int", "default": 10000, "desc": "最大字符数"},
    ],
    "accepts_body": False,
    "prompt": (
        "3. file_read：读取文件内容。必需参数 file 指定文件路径，可选 max_chars 限制读取字符数（默认 10000）。\n"
        "   示例：\n"
        + "   " + _A + ' type="file_read" id="read1" file="data.txt" max_chars="10000"' + _RB + _C + "\n"
    ),
}

_DEFAULT_MAX = 10000


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}

    path = ctx.resolve_path(file_)
    if not os.path.exists(path):
        return {"success": False, "summary": "文件不存在", "error": "文件不存在: " + path,
                "feedback": "文件不存在: " + path}

    file_size = os.path.getsize(path)
    try:
        max_chars = int(params.get("max_chars", _DEFAULT_MAX))
    except (ValueError, TypeError):
        max_chars = _DEFAULT_MAX

    with open(path, "r", encoding="utf-8") as f:
        content = f.read(max_chars)
        truncated = f.read(1) != ""

    lines = content.splitlines()
    n = len(lines)
    pad = len(str(n)) if n else 1
    numbered = "\n".join(f"{i:>{pad}}| {line}" for i, line in enumerate(lines, 1))

    summary = f"读取 {n} 行, {ctx.format_size(file_size)}" + (" (截断)" if truncated else "")
    feedback = (
        f"文件读取成功: {path}\n"
        f"{n} 行, {ctx.format_size(file_size)}"
        + (f" (仅读取前 {max_chars} 字符)" if truncated else "")
        + f"\n内容:\n{numbered}"
    )
    return {
        "success": True, "summary": summary, "error": None, "feedback": feedback,
        "info": {"path": path, "lines": n, "size": file_size, "truncated": truncated,
                 "output": numbered[:2000]},
    }
