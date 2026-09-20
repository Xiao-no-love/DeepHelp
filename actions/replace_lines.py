
"""技能：replace_lines — 按行号精确替换文件内容

支持单段与多段模式：
- 单段：start / end / expect 参数
- 多段：body 用 `@@ start-end` 头一次改多处，全部基于同一份文件快照、从下往上应用，
  从根本上避免"改完一处导致后续行号漂移"的问题。
"""

import os
import re

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "replace_lines",
    "icon": "fa-solid fa-scissors",
    "label": "行替换",
    "color": "#38bdf8",
    "order": 90,
    "description": "按行号精确替换文件内容（支持多段一次替换，避免行号漂移）",
    "params": [
        {"name": "file", "required": True, "desc": "文件路径"},
        {"name": "start", "required": False, "type": "int", "desc": "起始行号（单段模式；多段模式由 @@ 头指定）"},
        {"name": "end", "required": False, "type": "int", "desc": "结束行号（默认等于 start）"},
        {"name": "expect", "required": False, "desc": "锚点校验：原 start-end 行必须包含该文本，否则拒绝替换"},
        {"name": "rollback", "required": False, "type": "bool", "default": True, "desc": "失败自动回滚"},
    ],
    "accepts_body": True,
    "prompt": (
        "9. replace_lines：按行号精确替换文件内容（推荐用于简单修改，无需 diff 格式）。\n"
        "   【单段】参数 file（必需）、start（起始行号）、end（可选，默认=start）、\n"
        "   expect（可选，锚点校验：原 start-end 行必须包含该文本，否则拒绝并回显实际内容）、\n"
        "   rollback（可选，true/false，默认true）。body 为新内容（空 body 表示删除该范围所有行）。\n"
        "   【多段·强推荐】要改同一个文件的多处时，**务必用一次调用改完**，body 里用 @@ 头分段；\n"
        "   系统基于同一份文件快照、从下往上应用，彻底避免「改了一处导致后续行号漂移」。body 格式：\n"
        "     @@ 740-744\n"
        "     第一处的新内容\n"
        "     @@ 800\n"
        "     第二处的新内容（单行用 @@ 800，不写 -end）\n"
        "   @@ 头后可跟 expect 做锚点校验：@@ 740-744 expect=function send()\n"
        "   替换成功后会回显「被移除的内容」和「行数增减」，请据此核对是否误伤。\n"
        "   示例：\n"
        + "   " + _A + ' type="replace_lines" id="rl1" file="app.py" start="5"' + _RB + "\n"
        + "替换后的新行内容\n"
        + _C + "\n"
    ),
}

_HDR = re.compile(r"^@@\s*(\d+)(?:\s*-\s*(\d+))?\s*(?:expect\s*[=:]\s*(.+))?$")


def _as_bool(v, default=True):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes", "on")


def _strip_quotes(s):
    s = (s or "").strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _parse_segments(body):
    """把 body 解析成段列表；无 @@ 头返回 None（表示走单段模式）。"""
    lines = body.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        m = _HDR.match(ln.strip())
        if m:
            heads.append((i, m))
    if not heads:
        return None
    segs = []
    for idx, (i, m) in enumerate(heads):
        s = int(m.group(1))
        e = int(m.group(2)) if m.group(2) else s
        expect = _strip_quotes(m.group(3))
        end_i = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        content = lines[i + 1:end_i]
        segs.append({"start": s, "end": e, "expect": expect, "content": content})
    return segs


def _fail(msg, extra=None):
    d = {"success": False, "summary": msg, "error": msg, "feedback": msg}
    if extra:
        d["info"] = extra
    return d


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return _fail("缺少 file 参数")

    rollback = _as_bool(params.get("rollback"), True)
    abs_path = ctx.resolve_path(file_)

    if not os.path.exists(abs_path):
        return _fail("文件不存在: " + abs_path)

    with open(abs_path, "r", encoding="utf-8", newline="") as f:
        original_full = f.read()
    original_lines = original_full.splitlines()
    has_trailing_newline = original_full.endswith("\n")
    total = len(original_lines)

    # ---- 解析段：多段（@@）或单段（params） ----
    segs = _parse_segments(body) if body else None
    if segs is None:
        try:
            start = int(params.get("start", 0))
        except (ValueError, TypeError):
            start = 0
        if start < 1:
            return _fail("start 参数无效（单段模式必须提供 start）")
        end_raw = params.get("end")
        if end_raw is None:
            end = start
        else:
            try:
                end = int(end_raw)
            except (ValueError, TypeError):
                end = start
        segs = [{"start": start, "end": end,
                 "expect": _strip_quotes(params.get("expect")),
                 "content": body.splitlines() if body else []}]

    if not segs:
        return _fail("没有可替换的区段")

    # ---- 校验各段范围与锚点（全部基于原始快照） ----
    for sg in segs:
        s, e = sg["start"], sg["end"]
        if s < 1 or e > total or s > e:
            return _fail(
                "行范围无效: start=%d end=%d, 文件共 %d 行" % (s, e, total),
                {"total_lines": total})
        if sg["expect"]:
            seg_text = "\n".join(original_lines[s - 1:e])
            if sg["expect"] not in seg_text:
                return _fail(
                    "锚点校验失败: 第 %d-%d 行不含「%s」；实际内容:\n%s"
                    % (s, e, sg["expect"], seg_text[:500]))

    # ---- 重叠检查 ----
    ordered = sorted(segs, key=lambda x: x["start"])
    for a, b in zip(ordered, ordered[1:]):
        if b["start"] <= a["end"]:
            return _fail("替换区段重叠: 第 %d-%d 与 %d-%d"
                         % (a["start"], a["end"], b["start"], b["end"]))

    # ---- 应用：从下往上，避免偏移 ----
    result = list(original_lines)
    removed_all = []
    for sg in sorted(segs, key=lambda x: x["start"], reverse=True):
        s, e = sg["start"], sg["end"]
        removed_all.append((s, e, list(result[s - 1:e])))
        result[s - 1:e] = sg["content"]
    removed_all.sort(key=lambda x: x[0])  # 回显按行号正序

    new_text = "\n".join(result)
    if has_trailing_newline:
        new_text += "\n"

    # ---- 写入 + 校验 + 回滚 ----
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
            try:
                with open(abs_path, "w", encoding="utf-8", newline="") as f:
                    f.write(original_full)
            except Exception:
                pass
        return _fail("替换失败: " + str(e))
    except Exception as e:
        if rollback and applied:
            try:
                with open(abs_path, "w", encoding="utf-8", newline="") as f:
                    f.write(original_full)
            except Exception:
                pass
        return _fail("替换异常: " + str(e))

    # ---- 组装反馈：回显被移除内容 + 行数增减 ----
    delta = len(result) - total
    removed_lines = []
    for _, _, rl in removed_all:
        removed_lines.extend(rl)
    removed_preview = "\n".join(removed_lines)
    truncated = False
    if len(removed_preview) > 1200:
        removed_preview = removed_preview[:1200]
        truncated = True

    seg_desc = ", ".join("第%d-%d行" % (s, e) for s, e, _ in removed_all)
    delta_str = ("+" if delta >= 0 else "") + str(delta)
    fb = (
        "替换成功: %d 段 (%s), 行数 %d -> %d (%s)\n"
        "已移除内容:\n%s%s"
        % (len(segs), seg_desc, total, len(result), delta_str,
           removed_preview, "\n...(略)" if truncated else "")
    )
    return {
        "success": True,
        "summary": "替换成功 (%d 段, 行数 %s)" % (len(segs), delta_str),
        "error": None,
        "feedback": fb,
        "info": {"file": abs_path, "segments": len(segs),
                 "delta": delta, "total_before": total, "total_after": len(result)},
    }