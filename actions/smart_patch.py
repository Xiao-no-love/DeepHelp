
"""技能：smart_patch — 智能补丁（unified diff，预校验→应用→校验→回滚）"""

import io
import os

try:
    import whatthepatch
    from whatthepatch import apply as _wt_apply
except ImportError:
    whatthepatch = None
    _wt_apply = None

_LB = "<"
_RB = ">"
_DQ = chr(34)
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "smart_patch",
    "icon": "fa-solid fa-wand-magic-sparkles",
    "label": "智能补丁",
    "color": "#a78bfa",
    "order": 80,
    "description": "智能补丁（unified diff，预校验→应用→校验，支持自动回滚）",

    "params": [
        {"name": "file", "required": True, "desc": "文件路径"},
        {"name": "context", "required": False, "type": "int", "default": 5, "desc": "上下文行数"},
        {"name": "rollback", "required": False, "type": "bool", "default": True, "desc": "失败自动回滚"},
    ],
    "accepts_body": True,
    "prompt": (
        "8. smart_patch：智能补丁（推荐）。流程：预校验 → 应用补丁 → 修改后校验，支持自动回滚。\n"
        "   参数：file（必需），context（可选，上下文行数，默认5），rollback（可选，true/false，默认true）。\n"
        "   body必须为标准 unified diff 格式，diff 各行之间必须保留真实换行符，不可用空格替代。\n"
        "   diff 内容中的特殊字符必须进行 XML 实体转义。\n"
        "   【关键约束——违反以下任一条都会导致补丁被拒绝】\n"
        "   a) hunk header @@ -A,B +C,D @@ 中的行数 B 和 D 必须精确等于 body 中实际展示的旧行数和新行数，不允许估算。\n"
        "   b) 不得省略 hunk 范围内的尾部上下文行。如果 header 声明 7 行，body 必须完整展示 7 行旧内容 + 7 行新内容。\n"
        "   c) hunk 边界必须覆盖所有受影响的旧行——如果某行会被新增内容「顶到后面」，必须将其纳入 hunk 并标记为删除(-)。\n"
        "   d) 连续修改的不同区域必须拆分为多个 hunk，每个 hunk 独立校验。\n"
        "   示例（含双 hunk，注意尾部上下文完整，行数精确）：\n"
        + "   " + _A + ' type="smart_patch" id="sp1" file="app.py"' + _RB + "\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def old_func():\n"
        "-    print(" + _DQ + "old" + _DQ + ")\n"
        "+    print(" + _DQ + "new" + _DQ + ")\n"
        "     return 0\n"
        "@@ -10,4 +10,7 @@\n"
        "     pass\n"
        "\n"
        "\n"
        "-old_call()\n"
        "+if __name__ == " + _DQ + "__main__" + _DQ + ":\n"
        "+    old_call()\n"
        "+    print(" + _DQ + "done" + _DQ + ")\n"
        "+\n"
        + _C + "\n"
    ),
}

_DEFAULT_CONTEXT = 5


def _as_bool(v, default=True):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes", "on")


def _validate(patch, original_lines):
    try:
        _wt_apply.apply_diff(patch, list(original_lines))
        return True, "预校验通过"
    except Exception as e:
        return False, "预校验失败: " + str(e)


def _apply(patch, original_lines, has_trailing_newline):
    try:
        result_lines = _wt_apply.apply_diff(patch, list(original_lines))
        new_text = "\n".join(result_lines)
        if has_trailing_newline:
            new_text += "\n"
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            if marker in new_text:
                return False, None, "补丁应用后存在冲突标记"
        return True, new_text, ""
    except Exception as e:
        return False, None, "补丁应用失败: " + str(e)


def run(ctx, params, body):
    if whatthepatch is None:
        return {"success": False, "summary": "缺少依赖", "error": "缺少 whatthepatch",
                "feedback": "缺少依赖库 whatthepatch，无法执行智能补丁"}

    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}

    try:
        context = int(params.get("context", _DEFAULT_CONTEXT))
    except (ValueError, TypeError):
        context = _DEFAULT_CONTEXT
    rollback = _as_bool(params.get("rollback"), True)

    abs_path = ctx.resolve_path(file_)

    if not os.path.exists(abs_path):
        return {"success": False, "summary": "文件不存在",
                "error": "文件不存在: " + abs_path,
                "feedback": "文件不存在: " + abs_path}

    diff_file = io.StringIO(body)
    patches = list(whatthepatch.parse_patch(diff_file))
    if not patches:
        return {"success": False, "summary": "补丁解析失败", "error": "补丁解析失败",
                "feedback": "补丁解析失败：没有有效的补丁条目"}
    patch = patches[0]

    with open(abs_path, "r", encoding="utf-8", newline="") as f:
        original_full = f.read()
    original_lines = original_full.splitlines()
    has_trailing_newline = original_full.endswith("\n")

    valid, msg = _validate(patch, original_lines)
    if not valid:
        return {"success": False, "summary": "补丁预校验失败", "error": msg,
                "feedback": "补丁预校验失败: " + msg}

    ok, new_text, err = _apply(patch, original_lines, has_trailing_newline)
    if not ok:
        return {"success": False, "summary": "补丁应用失败", "error": err,
                "feedback": "补丁应用失败: " + err}

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
        reason = str(e)
        if reason == "无变化":
            return {"success": False, "summary": "校验失败", "error": "无变化已回滚",
                    "feedback": "校验失败，已自动回滚：文件内容未发生任何变化"}
        return {"success": False, "summary": "校验失败", "error": "写入校验失败已回滚",
                "feedback": "校验失败，已自动回滚：写入内容与预期结果不一致"}
    except Exception as e:
        if rollback and applied:
            try:
                with open(abs_path, "w", encoding="utf-8", newline="") as f:
                    f.write(original_full)
            except Exception:
                pass
        return {"success": False, "summary": "执行异常", "error": str(e),
                "feedback": "智能补丁执行异常: " + str(e)}

    return {
        "success": True, "summary": "智能补丁成功",
        "feedback": "智能补丁应用成功 (文件 " + abs_path + ")",
        "info": {"file": abs_path, "context": context},
    }
