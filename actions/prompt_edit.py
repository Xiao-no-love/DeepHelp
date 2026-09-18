
"""技能：prompt_edit — 读写本 AI 的 prompt.json（人设/自我规则/经验笔记）

路径由 prompt 模块统一管理（PROMPT_FILE），本技能不自行拼路径，
因此无论开发态还是打包态都能正确定位。
"""

_LT = chr(60)
_GT = chr(62)
_A = _LT + "action"
_C = _LT + "/action" + _GT

META = {
    "type": "prompt_edit",
    "icon": "fa-solid fa-brain",
    "label": "编辑提示词",
    "color": "#c084fc",
    "order": 111,
    "description": "读写自己的 prompt.json（persona/self_rules/notes/format_rules），路径自动定位",
    "params": [
        {"name": "field", "required": True, "desc": "目标字段：persona / self_rules / notes / format_rules"},
        {"name": "mode", "required": False, "desc": "set(覆盖，默认) / append(追加) / read(读取)"},
    ],
    "accepts_body": True,
    "prompt": (
        "11. prompt_edit：读写自己的 prompt.json（人设 persona / 自我规则 self_rules / 经验笔记 notes / 输出格式 format_rules）。\n"
        "    路径由系统自动定位，无需手动指定文件位置。\n"
        "    参数 field（必填：persona/self_rules/notes/format_rules）、mode（可选：set 覆盖 / append 追加 / read 读取，默认 set）。\n"
        "    body 为要写入的内容（mode=read 时 body 可留空）。\n"
        "    示例（把一条新经验追加到 notes）：\n"
        + "    " + _A + ' type="prompt_edit" id="pe1" field="notes" mode="append"' + _GT
        + "\n- 新经验内容\n" + _C + "\n"
        "    示例（读取当前 notes）：\n"
        + "    " + _A + ' type="prompt_edit" id="pe2" field="notes" mode="read"' + _GT + _C + "\n"
        "    注意：改完 prompt.json 后立即按照写入的规则生效。\n"
    ),
}

_VALID_FIELDS = ("persona", "self_rules", "notes", "format_rules")


def _fail(msg):
    return {"success": False, "summary": msg, "error": msg, "feedback": msg}


def run(ctx, params, body):
    try:
        import prompt as prompt_mod
    except Exception as e:
        return _fail("无法导入 prompt 模块: " + str(e))

    field = (params.get("field") or "").strip()
    mode = (params.get("mode") or "set").strip().lower()

    # 读取模式：返回三个字段现状
    if mode == "read":
        data = prompt_mod.load_prompt()
        path = getattr(prompt_mod, "PROMPT_FILE", "?")
        parts = ["prompt.json 位置: " + str(path)]
        for k in _VALID_FIELDS:
            v = data.get(k, "")
            parts.append("\n【" + k + "】\n" + (v if v else "(空)"))
        text = "\n".join(parts)
        return {
            "success": True,
            "summary": "已读取 prompt.json",
            "feedback": text,
            "info": {"path": str(path)},
        }

    if field not in _VALID_FIELDS:
        return _fail("field 必须是 persona / self_rules / notes 之一，收到: " + repr(field))

    if mode not in ("set", "append"):
        return _fail("mode 必须是 set / append / read 之一，收到: " + repr(mode))

    data = prompt_mod.load_prompt()
    old = data.get(field, "") or ""

    if mode == "append":
        if body is None:
            body = ""
        new = old.rstrip("\n")
        if new:
            new += "\n"
        new += body
    else:  # set
        new = body if body is not None else ""

    data[field] = new
    ok = prompt_mod.save_prompt(data)
    if not ok:
        return _fail("写入 prompt.json 失败")

    path = getattr(prompt_mod, "PROMPT_FILE", "?")
    action_word = "追加" if mode == "append" else "覆盖"
    return {
        "success": True,
        "summary": action_word + " " + field + " 成功（" + str(len(new)) + " 字符）",
        "feedback": (
            "prompt.json 的 " + field + " 已" + action_word + "，当前 "
            + str(len(new)) + " 字符。\n文件: " + str(path)
            + "\n注意：需重新点“初始化”注入系统提示词后才生效。"
        ),
        "info": {"path": str(path), "field": field, "mode": mode, "char_count": len(new)},
    }
