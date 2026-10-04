
"""技能：replace_lines — 按行号/内容锚点精确替换文件内容

支持单段与多段模式：
- 单段：start / end / expect 参数
- 多段：body 用 `@@` 头一次改多处，全部基于同一份文件快照、从下往上应用，
  从根本上避免"改完一处导致后续行号漂移"的问题。

@@ 头的两种寻址方式（可混用）：
- 行号模式：`@@ 740-744` / `@@ 800`
- 内容锚点模式（推荐，免疫行号漂移）：
    `@@ ~文本`       搜索【包含】该文本的行（要求全文件唯一）
    `@@ =文本`       搜索【strip 后精确等于】该文本的行（要求唯一）
    `@@ ~文本 +N`    从命中行起，往后共 N+1 行
  锚点命中 0 行或多行都会拒绝（后者列出所有命中行号）。
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
        {"name": "expect", "required": False, "desc": "锚点校验：原 start-end 行必须包含该文本（支持 a|b 多锚点，全部命中才通过），否则拒绝替换并回显该范围实际内容"},
        {"name": "context", "required": False, "type": "int", "default": 3, "desc": "成功后回显改动区前后各 N 行（默认3）"},
        {"name": "rollback", "required": False, "type": "bool", "default": True, "desc": "失败自动回滚"},
    ],
    "accepts_body": True,
    "prompt": (
        "9. replace_lines：按行号或内容锚点精确替换文件内容（推荐用于简单修改，无需 diff 格式）。\n"
        "   【单段】参数 file（必需）、start（起始行号）、end（可选，默认=start）、\n"
        "   expect（可选，锚点校验：原 start-end 行须包含该文本，支持 a|b 多锚点全部命中，否则拒绝并回显实际内容；见反馈）、\n"
        "   rollback（可选，true/false，默认true）。body 为新内容（空 body 表示删除该范围所有行）。\n"
        "   【多段·强推荐】要改同一个文件的多处时，**务必用一次调用改完**，body 里用 @@ 头分段；\n"
        "   系统基于同一份文件快照、从下往上应用，彻底避免「改了一处导致后续行号漂移」。\n"
        "   @@ 头两种寻址【可混用】：\n"
        "     (a) 行号：@@ 740-744 或 @@ 800（单行不写 -end）\n"
        "     (b) 内容锚点【免疫漂移，首选】：@@ ~文本（含该文本的行）/ @@ =文本（strip 后精确等于）\n"
        "         @@ ~文本 +N 表示从命中行起往后共 N+1 行；锚点须全文件唯一，命中 0/多行都拒绝（多行会列出行号）\n"
        "   @@ 头后可跟 expect 做二次校验，支持 a|b 多锚点：@@ ~def send +4 expect=def send|return\n"
        "   替换成功后会回显「各段行号映射(原->新)」「被移除内容」「改动区前后上下文」和行数增减，请据此核对是否误伤。\n"
        "   示例：\n"
        + "   " + _A + ' type="replace_lines" id="rl1" file="app.py" start="5"' + _RB + "\n"
        + "替换后的新行内容\n"
        + _C + "\n"
    ),
}

_HDR_LINE = re.compile(r"^@@\s*(\d+)(?:\s*-\s*(\d+))?\s*(?:expect\s*[=:]\s*(.+))?$")
_HDR_ANCHOR = re.compile(r"^@@\s*([~=])\s*(.+?)(?:\s*\+\s*(\d+))?\s*(?:\bexpect\s*[=:]\s*(.+))?$")
_HDR = _HDR_LINE  # 兼容旧引用


def _as_bool(v, default=True):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes", "on")


def _strip_quotes(s):
    s = (s or "").strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _split_expect(expect):
    """把 expect 串按 | 拆成多锚点列表（strip 空白，去空项）。"""
    if not expect:
        return []
    return [t.strip() for t in expect.split("|") if t.strip()]


def _parse_segments(body):
    """把 body 解析成段列表；无 @@ 头返回 None（表示走单段模式）。

    每段形如 {"mode": "line"|"anchor", "start", "end", "expect", "content", ...}
    - line 段：已确定 start/end
    - anchor 段：带 anchor_kind(~/=)、anchor_text、span，行号待 _resolve_anchor 解析
    """
    lines = body.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        raw = ln.strip()
        m = _HDR_LINE.match(raw)
        if m:
            heads.append((i, "line", m))
            continue
        m = _HDR_ANCHOR.match(raw)
        if m:
            heads.append((i, "anchor", m))
    if not heads:
        return None
    segs = []
    for idx, (i, kind, m) in enumerate(heads):
        end_i = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        content = lines[i + 1:end_i]
        if kind == "line":
            s = int(m.group(1))
            e = int(m.group(2)) if m.group(2) else s
            expect = _strip_quotes(m.group(3))
            segs.append({"mode": "line", "start": s, "end": e,
                         "expect": expect, "content": content})
        else:
            akind = m.group(1)          # ~ 或 =
            atext = _strip_quotes(m.group(2))
            span = int(m.group(3)) if m.group(3) else 0
            expect = _strip_quotes(m.group(4))
            segs.append({"mode": "anchor", "anchor_kind": akind,
                         "anchor_text": atext, "span": span,
                         "expect": expect, "content": content})
    return segs


def _resolve_anchor(seg, original_lines):
    """把 anchor 段解析成 line 段（就地补 start/end）。返回 None 成功，否则返回错误信息。"""
    text = seg["anchor_text"]
    kind = seg["anchor_kind"]
    hits = []
    for i, ln in enumerate(original_lines):
        if kind == "=":
            ok = (ln.strip() == text)
        else:  # ~
            ok = (text in ln)
        if ok:
            hits.append(i + 1)  # 1-based
    if not hits:
        return "锚点未命中: %s%s（文件中无匹配行）" % (kind, text)
    if len(hits) > 1:
        return "锚点歧义: %s%s 命中 %d 行（第 %s 行），请加长锚点或改用行号模式" % (
            kind, text, len(hits), ", ".join(str(h) for h in hits[:10]))
    s = hits[0]
    seg["start"] = s
    seg["end"] = s + seg.get("span", 0)
    seg["mode"] = "line"
    return None


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
    if "\r\n" in original_full:
        eol = "\r\n"
    elif "\r" in original_full:
        eol = "\r"
    else:
        eol = "\n"
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
        segs = [{"mode": "line", "start": start, "end": end,
                 "expect": _strip_quotes(params.get("expect")),
                 "content": body.splitlines() if body else []}]

    if not segs:
        return _fail("没有可替换的区段")

    # ---- 解析 anchor 段为行号（基于原始快照定位） ----
    for sg in segs:
        if sg.get("mode") == "anchor":
            err = _resolve_anchor(sg, original_lines)
            if err:
                return _fail(err, {"total_lines": total})


    # ---- 校验各段范围与锚点（全部基于原始快照） ----
    for sg in segs:
        s, e = sg["start"], sg["end"]
        if s < 1 or e > total or s > e:
            return _fail(
                "行范围无效: start=%d end=%d, 文件共 %d 行" % (s, e, total),
                {"total_lines": total})
        anchors = _split_expect(sg["expect"])
        if anchors:
            seg_text = "\n".join(original_lines[s - 1:e])
            missing = [a for a in anchors if a not in seg_text]
            if missing:
                numbered = "\n".join(
                    "%d| %s" % (s + k, original_lines[s - 1 + k])
                    for k in range(e - s + 1))
                return _fail(
                    "锚点校验失败: 第 %d-%d 行未命中锚点 %s；该范围实际内容（带行号）:\n%s"
                    % (s, e, missing, numbered[:800]))

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

    new_text = eol.join(result)
    if has_trailing_newline:
        new_text += eol

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

    # 各段「原行号 -> 新行号」映射（按 start 正序，累计前面各段 delta）
    try:
        ctx_n = int(params.get("context", 3))
    except (ValueError, TypeError):
        ctx_n = 3
    if ctx_n < 0:
        ctx_n = 0

    ordered_segs = sorted(segs, key=lambda x: x["start"])
    map_lines = []
    cum = 0
    for sg in ordered_segs:
        s, e = sg["start"], sg["end"]
        new_cnt = len(sg["content"])
        new_s = s + cum
        new_e = new_s + new_cnt - 1 if new_cnt > 0 else new_s - 1
        map_lines.append((s, e, new_s, new_e))
        cum += new_cnt - (e - s + 1)

    map_str = "\n".join(
        "  第%d-%d行 -> 第%d-%d行" % (s, e, ns, ne) if ne >= ns
        else "  第%d-%d行 -> (删除)" % (s, e)
        for s, e, ns, ne in map_lines)

    ctx_str = ""
    if ctx_n > 0:
        parts = []
        for s, e, ns, ne in map_lines:
            lo = max(0, ns - 1 - ctx_n)
            hi = min(len(result), ne + ctx_n)
            block = "\n".join(
                "%s%d| %s" % (">>> " if ns <= (lo + 1 + k) <= ne and ne >= ns else "    ",
                              lo + k + 1, result[lo + k])
                for k in range(hi - lo))
            parts.append("  [原第%d-%d行 改后]\n%s" % (s, e, block))
        ctx_str = "\n改动区上下文(前后各%d行):\n%s" % (ctx_n, "\n".join(parts))

    fb = (
        "替换成功: %d 段 (%s), 行数 %d -> %d (%s)\n"
        "各段行号映射:\n%s\n"
        "已移除内容:\n%s%s%s"
        % (len(segs), seg_desc, total, len(result), delta_str,
           map_str, removed_preview, "\n...(略)" if truncated else "", ctx_str)
    )
    return {
        "success": True,
        "summary": "替换成功 (%d 段, 行数 %s)" % (len(segs), delta_str),
        "error": None,
        "feedback": fb,
        "info": {"file": abs_path, "segments": len(segs),
                 "delta": delta, "total_before": total, "total_after": len(result),
                 "mapping": [{"old": [s, e], "new": [ns, ne]} for s, e, ns, ne in map_lines]},
    }