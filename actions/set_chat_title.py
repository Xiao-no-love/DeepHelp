
"""技能：set_chat_title — 修改 DeepSeek 网页当前会话的标题（模拟点击 UI）

注意：Playwright sync API 不能在有运行中 asyncio loop 的线程里启动
（DeepHelp 主线程跑 pywebview，带着 asyncio loop）。故把整个改标题流程
丢到独立线程执行——新线程无 asyncio loop，sync API 可用。
"""

import threading

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


def _do_change_title(port, title):
    """真正的改标题逻辑（在独立线程里跑 asyncio.run，避开主线程事件循环）。

    注意：用 async API 而非 sync API——因为 DeepHelp 的 agent 已启动过一个
    sync_playwright 实例，sync API 在同一进程内启动两次会报错；async API
    可重复启动，不受此限。
    """
    import asyncio
    from playwright.async_api import async_playwright

    async def _inner():
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:%d" % port)
            page = None
            for c in browser.contexts:
                for pg in c.pages:
                    if "chat.deepseek.com" in (pg.url or ""):
                        page = pg
                        break
                if page:
                    break
            if page is None:
                await browser.close()
                return {"success": False, "summary": "未找到 DeepSeek 页面",
                        "error": "no deepseek page",
                        "feedback": "未找到 DeepSeek 聊天页面（请确认已连接 Chrome 并打开对话）"}

            has_input = await page.evaluate(
                "() => !!document.querySelector('.the-header input.ds-input__input')")
            if not has_input:
                clickable = page.locator('.the-header [tabindex="0"]').first
                if await clickable.count() == 0:
                    await browser.close()
                    return {"success": False, "summary": "未找到标题元素",
                            "error": "no title element",
                            "feedback": "未找到标题元素（页面结构可能已变化）"}
                await clickable.click()

            await asyncio.sleep(0.4)
            inp = page.locator('.the-header input.ds-input__input').first
            if await inp.count() == 0:
                await browser.close()
                return {"success": False, "summary": "未出现标题输入框",
                        "error": "no title input",
                        "feedback": "点击后未出现标题输入框（页面结构可能已变化）"}
            old = await inp.input_value()
            await inp.fill("")
            await inp.fill(title)
            await inp.press("Enter")
            await asyncio.sleep(0.6)
            await browser.close()

        return {"success": True,
                "summary": "会话标题已改为：" + title,
                "feedback": "已将 DeepSeek 会话标题从「%s」改为「%s」" % (old, title),
                "info": {"old_title": old, "new_title": title}}

    return asyncio.run(_inner())


def run(ctx, params, body):
    title = (params.get("title") or params.get("name") or (body or "")).strip()
    if not title:
        return {"success": False, "summary": "缺少标题",
                "error": "缺少标题", "feedback": "set_chat_title 需要 title 参数或 body"}

    port = _get_port(ctx)
    try:
        import playwright  # noqa: F401
    except Exception as e:
        return {"success": False, "summary": "playwright 不可用", "error": str(e),
                "feedback": "playwright 不可用：" + str(e)}

    _box = {}

    def _worker():
        try:
            _box["result"] = _do_change_title(port, title)
        except Exception as e:
            _box["err"] = str(e)

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(timeout=30)
    if th.is_alive():
        return {"success": False, "summary": "改标题超时", "error": "timeout",
                "feedback": "改会话标题超时（>30s）"}
    if _box.get("err"):
        return {"success": False, "summary": "改标题异常", "error": _box["err"],
                "feedback": "改会话标题异常：" + _box["err"]}
    return _box.get("result", {"success": False, "summary": "未知错误", "error": "no result",
                               "feedback": "改会话标题未返回结果"})