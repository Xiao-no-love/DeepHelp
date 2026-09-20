
"""技能：python_reset — 重置 Python 执行环境"""

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "python_reset",
    "icon": "fa-solid fa-rotate",
    "label": "重置Python",
    "color": "#f472b6",
    "order": 100,
    "description": "重置 Python 执行环境，清除所有已定义的变量和导入的模块",
    "params": [],
    "accepts_body": False,
    "prompt": (
        "10. python_reset：重置 Python 执行环境，清除所有已定义的变量和导入的模块。\n"
        "    示例：\n"
        + "    " + _A + ' type="python_reset" id="reset1"' + _RB + _C + "\n"
    ),
}


def run(ctx, params, body):
    ctx.python_executor.reset()
    return {"success": True, "summary": "Python 环境已重置",
            "feedback": "Python 执行环境已重置", "info": {}}
