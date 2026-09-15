
"""技能：python — 执行 Python 代码"""

import os

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "python",
    "icon": "fa-brands fa-python",
    "label": "Python",
    "color": "#c084fc",
    "order": 10,
    "description": "执行 Python 代码",
    "params": [
        {"name": "cwd", "required": False, "desc": "工作目录（不填则用当前目录）"},
    ],
    "accepts_body": True,
    "prompt": (
        "1. python：执行Python代码（body内为代码）。支持可选参数 cwd 指定工作目录。\n"
        "   示例：\n"
        + "   " + _A + ' type="python" id="example1"' + _GT
        + '\nprint("Hello, 老板")\n' + _C + "\n"
    ),
}


def run(ctx, params, body):
    cwd = params.get("cwd")
    old_cwd = None
    if cwd:
        target = ctx.resolve_path(cwd)
        if os.path.isdir(target):
            old_cwd = os.getcwd()
            os.chdir(target)

    try:
        out, err = ctx.python_executor.execute(body)
    finally:
        if old_cwd is not None:
            os.chdir(old_cwd)

    preview = body.strip()[:200]
    if err:
        return {
            "success": False, "summary": "执行失败", "error": err,
            "feedback": "Python 执行失败\n错误: " + err + "\n输出:\n" + (out or "(无输出)"),
            "info": {"command": preview, "output": out, "cwd": cwd or ""},
        }
    return {
        "success": True, "summary": "执行成功",
        "feedback": "Python 执行成功\n输出:\n" + (out or "(无输出)"),
        "info": {"command": preview, "output": out or "(无输出)", "cwd": cwd or ""},
    }
