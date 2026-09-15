
"""技能：replace_lines — 按行号精确替换文件内容"""

import os

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "replace_lines",
    "icon": "fa-solid fa-scissors",
    "label": "行替换",
    "color": "#38bdf8",
    "order": 90,
    "description": "按行号精确替换文件内容（无需 diff 格式）",
    "params": [
        {"name": "file", "required": True, "desc": "文件路径"},

        {"name": "start", "required": True, "type": "int", "desc": "起始行号"},
        {"name": "end", "required": False, "type": "int", "desc": "结束行号（默认等于 start）"},
        {"name": "rollback", "required": False, "type": "bool", "default": True, "desc": "失败自动回滚"},
    ],
    "accepts_body": True,
    "prompt": (
        "9. replace_lines：按行号精确替换文件内容（推荐用于简单修改，无需 diff 格式）。\n"
        "   参数：file（必需），start（必需，起始行号），end（可选，结束行号，默认为 start 即单行替换），\n"
        "   rollback（可选，true/false，默认true）。body 为要写入的新内容（空 body 表示删除该范围内所有行）。\n"
        "   配合 file_read 输出的行号使用，精准可靠。示例：\n"
        + "   " + _A + ' type="replace_lines" id="rl1" file="app.py" start="5"' + _GT + "\n"
        + "替换后的新行内容\n"
        + _C + "\n"
        + "   " + _A + ' type="replace_lines" id="rl2" file="app.py" start="10" end="12"' + _GT + _C + "\n"
        + "   （删除第 10-12 行，body 为空）\n"
    ),
}


def _as_bool(v, default=True):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes", "on")


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}

    try:
        start = int(params.get("start", 0))
    except (ValueError, TypeError):
        start = 0
    if start < 1:
        return {"success": False, "summary": "start 参数无效", "error": "start 参数无效",
                "feedback": "start 参数无效"}

    end_raw = params.get("end")
    if end_raw is None:
        end = start
    else:
        try:
            end = int(end_raw)
        except (ValueError, TypeError):
            end = start

    rollback = _as_bool(params.get("rollback"), True)
    abs_path = ctx.resolve_path(file_)

    if not os.path.exists(abs_path):
        return {"success": False, "summary": "文件不存在",
                "error": "文件不存在: " + abs_path,
                "feedback": "文件不存在: " + abs_path}

    with open(abs_path, "r", encoding="utf-8", newline="") as f:
        original_full = f.read()
    original_lines = original_full.splitlines()
    has_trailing_newline = original_full.endswith("\n")
    total = len(original_lines)

    if start < 1 or end > total or start > end:
        return {"success": False, "summary": "行范围无效",
                "error": "行范围无效: start=" + str(start) + ", end=" + str(end) + ", 共 " + str(total) + " 行",
                "feedback": "行范围无效: start=" + str(start) + ", end=" + str(end) + ", 文件共 " + str(total) + " 行",
                "info": {"total_lines": total}}

    body_lines = body.splitlines() if body else []
    new_lines = original_lines[:start - 1] + body_lines + original_lines[end:]
    new_text = "\n".join(new_lines)
    if has_trailing_newline:
        new_text += "\n"

    applied = False
    try:
        with open(abs_path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        applied = True
        with open(abs_path, "r", encoding="utf-8", newline="") as f:
            new_full = f.read()
        if original_full == new_full:
            raise RuntimeError("无变化")
        if new_text != new_full:
            raise RuntimeError("写入校验失败")
    except RuntimeError as e:
        if rollback and applied:
            with open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(original_full)
        tag = "第 " + str(start) + "-" + str(end) + " 行"
        return {"success": False, "summary": "替换失败",
                "error": str(e),
                "feedback": "替换失败 (" + tag + "): " + str(e)}
    except Exception as e:
        if rollback and applied:
            try:
                with open(abs_path, "w", encoding="utf-8", newline="") as f:
                    f.write(original_full)
            except Exception:
                pass
        return {"success": False, "summary": "替换异常", "error": str(e),
                "feedback": "替换异常: " + str(e)}

    return {
        "success": True,
        "summary": "替换成功 (第 " + str(start) + "-" + str(end) + " 行 -> " + str(len(body_lines)) + " 行)",
        "feedback": "替换成功 (第 " + str(start) + "-" + str(end) + " 行, 文件 " + abs_path + ")",
        "info": {"file": abs_path, "start": start, "end": end},
    }
