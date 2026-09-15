
"""技能：python_reset — 重置 Python 执行环境"""

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

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
        + "    " + _A + ' type="python_reset" id="reset1"' + _GT + _C + "\n"
    ),
}


def run(ctx, params, body):
    ctx.python_executor.reset()
    return {"success": True, "summary": "Python 环境已重置",
            "feedback": "Python 执行环境已重置", "info": {}}
