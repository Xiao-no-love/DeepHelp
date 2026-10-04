"""DeepHelp — 本地对话流水（JSONL）写入器

单窗口信息本地化：把「用户输入 / 模型文本输出 / 工具调用元信息 / 会话URL」
追加写入 chat_logs/<session_id>.jsonl，每条一行 JSON，追加即落盘，
抗窗口意外关闭。

设计要点：
- 只记工具【元信息】（type/target/success/duration_ms），不记输出正文
  （正文体积大，audit.log 已有完整版，可交叉查）。
- 分类靠 "kind" 字段：user / assistant_text / tool / url / system。
- 全模块静默容错：日志功能绝不能影响主流程。
"""

import json
import os
import re
import time

# 日志根目录：与 api.py 同级的 chat_logs/
_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_HERE, "chat_logs")

# 从 DeepSeek 会话 URL 抽 UUID：.../a/chat/s/<uuid>
_UUID_RE = re.compile(r"/s/([0-9a-fA-F-]{8,})")


def session_id_from_url(url):
    """从会话 URL 解析 session_id；解析不到返回空串。"""
    if not url:
        return ""
    m = _UUID_RE.search(url)
    return m.group(1) if m else ""


def _path_for(session_id):
    os.makedirs(LOG_DIR, exist_ok=True)
    # 空 session_id → 落到 _pending.jsonl（未定会话的暂存区，前端不展示）
    sid = session_id or "_pending"
    # 防路径穿越：只留安全字符
    sid = re.sub(r"[^0-9A-Za-z_-]", "_", sid)
    return os.path.join(LOG_DIR, sid + ".jsonl")


def write(session_id, kind, **fields):
    """追加一条流水。失败静默——日志绝不拖垮主流程。

    空值过滤：user / assistant_text 若 text 去空白后为空，则不写（避免空记录污染）。
    """
    try:
        if kind in ("user", "assistant_text"):
            _t = fields.get("text")
            if _t is None or str(_t).strip() == "":
                return
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": kind,
            "session": session_id or "",
        }
        if not session_id:
            entry["pending"] = True
        entry.update(fields)
        with open(_path_for(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
def record_url_with_title(session_id, url, title=""):
    """记录会话 URL + 标题（每次拿到新 URL/标题时调用）。"""
    write(session_id, "url", url=url or "", title=title or "")


def read_session(session_id):
    """读取某会话的全部流水，返回 list[dict]。失败返回空列表。"""
    out = []
    try:
        path = _path_for(session_id)
        if not os.path.isfile(path):
            return out
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def list_sessions():
    """扫描 chat_logs/ 目录，返回会话清单，按最后活动时间倒序。

    每个元素：{session_id, time, title, url, count}
    - time：取该会话最后一条记录的 ts（最后活动时间）
    - title/url：取该会话最后一条 kind=url 的记录（可能是后续更新的标题）
    """
    result = []
    try:
        if not os.path.isdir(LOG_DIR):
            return result
        for name in os.listdir(LOG_DIR):
            if not name.endswith(".jsonl"):
                continue
            sid = name[:-6]  # 去 .jsonl
            if sid.startswith("_"):
                continue  # _pending 等暂存文件，不作为会话展示
            records = read_session(sid)
            if not records:
                continue
            last = records[-1]
            title = ""
            url = ""
            for r in records:
                if r.get("kind") == "url":
                    title = r.get("title", "") or title
                    url = r.get("url", "") or url
            result.append({
                "session_id": sid,
                "time": last.get("ts", ""),
                "title": title,
                "url": url,
                "count": len(records),
            })
        result.sort(key=lambda x: x.get("time", ""), reverse=True)
    except Exception:
        pass
    return result