
"""技能：auto_mode — 自动模式开关（控制流级，运行时拦截）"""

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "auto_mode",
    "icon": "fa-solid fa-robot",
    "label": "自动模式",
    "color": "#22d3ee",
    "order": 110,
    "description": "开启/关闭自动模式：开启后，当你回复不含动作而停下时，系统会自动提示你继续推进任务，直到你主动关闭或达到轮数上限",
    "params": [],
    "accepts_body": True,
    "prompt": (
        "11. auto_mode：自动模式开关（控制流级，不产生文件/命令副作用）。\n"
        "    body 填 on 或 off。\n"
        "    - on：开启自动模式。此后当你不含动作直接回复时，系统会自动给你发"
        "「[系统提示] 继续推进任务」让你接着干，无需老板手动催。\n"
        "    - off：关闭自动模式。**达成目标后必须主动调用它关闭**；"
        "并在关闭前用 notice 给老板发一条完成通知（如「任务完成」+ 摘要）；"
        "若需要老板决策/确认，也要先 off 再用 quiz 提问。\n"
        "    示例：\n"
        "    " + _A + ' type="auto_mode" id="am1"' + _GT + "on" + _C + "\n"
        "    " + _A + ' type="auto_mode" id="am2"' + _GT + "off" + _C + "\n"
    ),
}


def run(ctx, params, body):
    # 该动作由 api._run_agent 运行时拦截处理，正常不会走到这里。
    cmd = (body or "").strip().lower()
    if cmd not in ("on", "off"):
        return {"success": False, "summary": "参数错误",
                "error": "auto_mode 的 body 必须是 on 或 off",
                "feedback": "auto_mode 参数错误：body 应为 on 或 off"}
    return {"success": True, "summary": "自动模式 " + cmd,
            "feedback": "自动模式 " + cmd, "info": {}}