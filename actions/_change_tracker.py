"""文件变更追踪内核（内部模块，非技能，文件名 _ 开头以跳过技能扫描）。

职责：记录本次会话中 AI 通过动作改动的文件（改/新增/删），并在动作执行前对目标
文件做快照，供 diff 查看与（可选）回滚。

关键设计：
- 挂钩点在 action.py 的 execute_action：文件类动作执行前 before()，执行后 after()。
- 快照存 service_logs/_change_snapshots/，二进制原样保存，避免编码问题。
- 每个文件记录首个快照（orig_snap，用于看"会话累计净变化"）与最近快照（last_snap）。
- 跨 skill 单例共享（经 sys.modules），与 _process_manager 同一套路。
"""

import os
import sys
import time
import difflib
import threading


_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR = os.environ.get("DH_CHANGE_SNAP_DIR") or os.path.join(_ROOT_DIR, "service_logs", "_change_snapshots")

# 会被追踪的文件类动作
FILE_ACTIONS = {"file_write", "file_append", "file_delete", "replace_lines", "smart_patch"}

# 单文件 diff 最大展示行数（防止超大文件把前端卡死）
MAX_DIFF_LINES = 400


def _norm(path):
    """归一化为用于比对的 key（Windows 大小写不敏感）。"""
    return os.path.normcase(os.path.abspath(path))


class ChangeTracker:
    def __init__(self):
        self._changes = {}          # key -> rec
        self._order = []            # key 列表，保持最近操作顺序
        self._lock = threading.Lock()
        self._seq = 0

    # ── 动作执行前：拍快照 ──
    def before(self, action_type, path):
        if action_type not in FILE_ACTIONS or not path:
            return None
        try:
            key = _norm(path)
            exists = os.path.exists(path)
            is_file = exists and os.path.isfile(path)
            data = b""
            if is_file:
                with open(path, "rb") as f:
                    data = f.read()
            self._seq += 1
            base = os.path.basename(path) or "file"
            snap_path = os.path.join(SNAP_DIR, "s%05d_%s" % (self._seq, base))
            with open(snap_path, "wb") as f:
                f.write(data)
            return {"key": key, "path": path, "snap_path": snap_path,
                    "existed": exists, "is_file": is_file, "size": len(data)}
        except Exception:
            return None

    # ── 动作执行后：记录变更 ──
    def after(self, action_type, path, snap, success):
        if not snap or not path:
            return
        try:
            key = snap["key"]
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            with self._lock:
                rec = self._changes.get(key)
                if rec is None:
                    rec = {
                        "path": path,
                        "key": key,
                        "ops": 0,
                        "actions": [],
                        "first_ts": now,
                        "last_ts": now,
                        "orig_snap": snap["snap_path"],
                        "orig_existed": snap["existed"],
                        "last_snap": snap["snap_path"],
                    }
                    self._changes[key] = rec
                    if key in self._order:
                        self._order.remove(key)
                    self._order.append(key)
                rec["ops"] += 1
                if action_type not in rec["actions"]:
                    rec["actions"].append(action_type)
                rec["last_ts"] = now
                rec["last_snap"] = snap["snap_path"]
                # 状态判定：以"当前是否存在"为准
                cur_exists = os.path.exists(path)
                if not cur_exists:
                    rec["status"] = "deleted"
                elif snap["existed"]:
                    rec["status"] = "modified"
                else:
                    rec["status"] = "created"
                rec["success"] = bool(success)
                try:
                    rec["size"] = os.path.getsize(path) if cur_exists else 0
                except Exception:
                    rec["size"] = 0
        except Exception:
            pass

    # ── 查询 ──
    def list_changes(self):
        with self._lock:
            out = []
            for key in reversed(self._order):   # 最近操作在前
                rec = self._changes.get(key)
                if not rec:
                    continue
                out.append({
                    "path": rec["path"],
                    "status": rec.get("status", "modified"),
                    "ops": rec["ops"],
                    "actions": list(rec["actions"]),
                    "first_ts": rec["first_ts"],
                    "last_ts": rec["last_ts"],
                    "size": rec.get("size", 0),
                    "success": rec.get("success", True),
                })
            return out

    def clear(self):
        with self._lock:
            self._changes = {}
            self._order = []
        return True

    # ── diff：首次快照 vs 当前 ──
    def get_diff(self, path):
        key = _norm(path)
        with self._lock:
            rec = self._changes.get(key)
        if not rec:
            return {"ok": False, "error": "该文件未被本次会话修改"}
        # 先按 orig_snap 看累计净变化；文件删除时直接提示
        snap_path = rec["orig_snap"]
        rel = rec["path"]
        cur_exists = os.path.exists(rel)
        old_text = self._read_text(snap_path)
        if not cur_exists:
            return {"ok": True, "path": rel, "status": "deleted",
                    "diff": "（文件已被删除）\n\n--- 原始内容 ---\n" + self._tail_text(old_text),
                    "truncated": False}
        new_text = self._read_text_file(rel)
        diff = self._make_diff(old_text, new_text, rel)
        truncated = False
        lines = diff.splitlines()
        if len(lines) > MAX_DIFF_LINES:
            diff = "\n".join(lines[:MAX_DIFF_LINES]) + "\n…（省略 %d 行）" % (len(lines) - MAX_DIFF_LINES)
            truncated = True
        return {"ok": True, "path": rel, "status": rec.get("status", "modified"),
                "diff": diff, "truncated": truncated}

    @staticmethod
    def _read_text(p):
        try:
            with open(p, "rb") as f:
                raw = f.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("gbk", errors="replace")
        except Exception:
            return ""

    def _read_text_file(self, p):
        try:
            with open(p, "rb") as f:
                raw = f.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("gbk", errors="replace")
        except Exception as e:
            return "<读取失败: %s>" % e

    @staticmethod
    def _tail_text(text, n=30):
        lines = text.splitlines()
        if len(lines) <= n:
            return text
        return "…\n" + "\n".join(lines[-n:])

    @staticmethod
    def _make_diff(old_text, new_text, path):
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        if old_text == new_text:
            return "（内容无变化）"
        d = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=path + "  (会话初始)",
            tofile=path + "  (当前)",
            lineterm="",
        )
        return "\n".join(d)


_manager = None
_manager_lock = threading.Lock()


def get_tracker():
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                try:
                    os.makedirs(SNAP_DIR, exist_ok=True)
                except Exception:
                    pass
                _manager = ChangeTracker()
    return _manager