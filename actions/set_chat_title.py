
"""技能：set_chat_title — 修改 DeepSeek 网页当前会话的标题（模拟点击 UI）"""

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "set_chat_title",
    "icon": "fa-solid fa-tag",
    "label": "改会话标题",
    "color": "#f472b6",
    "order": 113,
    "description": "修改 DeepSeek 网页当前会话的标题（模拟点击标题→输入→回车）",
    "params": [
        {"name": "title", "required": False, "desc": "新标题（也可写在 body）"},
    ],
    "accepts_body": True,
    "prompt": (
        "13. set_chat_title：修改 DeepSeek 网页当前会话的标题（让会话名反映任务内容，便于辨识）。\n"
        "    参数：title（可选，新标题，也可写在 body）。\n"
        "    适用场景：任务完成后把会话标题改成任务摘要、或老板要求重命名会话时。\n"
        "    注意：本动作通过模拟点击标题输入框实现，依赖 Chrome 调试端口可连。\n"
        "    示例：\n"
        "    " + _A + ' type="set_chat_title" id="t1" title="优化 DeepHelp 插话时序"' + _RB + _C + "\n"
    ),
}


def _get_port(ctx):
    """从配置读 Chrome 调试端口，读不到默认 9222。"""
    try:
        import os, json
        # 找 config.json：优先 ctx.work_dir，其次本项目根
        cands = []
        if getattr(ctx, "work_dir", None):
            cands.append(os.path.join(ctx.work_dir, "config.json"))
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cands.append(os.path.join(here, "config.json"))
        for c in cands:
            if os.path.isfile(c):
                with open(c, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                p = (cfg.get("chrome") or {}).get("port")
                if p:
                    return int(p)
    except Exception:
        pass
    return 9222


def run(ctx, params, body):
    title = (params.get("title") or params.get("name") or (body or "")).strip()
    if not title:
        return {"success": False, "summary": "缺少标题",
                "error": "缺少标题", "feedback": "set_chat_title 需要 title 参数或 body"}

    port = _get_port(ctx)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"success": False, "summary": "playwright 不可用", "error": str(e),
                "feedback": "playwright 不可用：" + str(e)}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:%d" % port)
            page = None
            for c in browser.contexts:
                for pg in c.pages:
                    if "chat.deepseek.com" in (pg.url or ""):
                        page = pg
                        break
                if page:
                    break
            if page is None:
                browser.close()
                return {"success": False, "summary": "未找到 DeepSeek 页面",
                        "error": "no deepseek page",
                        "feedback": "未找到 DeepSeek 聊天页面（请确认已连接 Chrome 并打开对话）"}

            # 进入编辑态：若已是 input 则跳过点击
            has_input = page.evaluate(
                "() => !!document.querySelector('.the-header input.ds-input__input')")
            if not has_input:
                clickable = page.locator('.the-header [tabindex="0"]').first
                if clickable.count() == 0:
                    browser.close()
                    return {"success": False, "summary": "未找到标题元素",
                            "error": "no title element",
                            "feedback": "未找到标题元素（页面结构可能已变化）"}
                clickable.click()

            import time
            time.sleep(0.4)
            inp = page.locator('.the-header input.ds-input__input').first
            if inp.count() == 0:
                browser.close()
                return {"success": False, "summary": "未出现标题输入框",
                        "error": "no title input",
                        "feedback": "点击后未出现标题输入框（页面结构可能已变化）"}
            old = inp.input_value()
            inp.fill("")
            inp.fill(title)
            inp.press("Enter")
            time.sleep(0.6)
            browser.close()
    except Exception as e:
        return {"success": False, "summary": "改标题异常", "error": str(e),
                "feedback": "改会话标题异常：" + str(e)}

    return {"success": True,
            "summary": "会话标题已改为：" + title,
            "feedback": "已将 DeepSeek 会话标题从「%s」改为「%s」" % (old, title),
            "info": {"old_title": old, "new_title": title}}