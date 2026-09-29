
"""技能：file_delete — 删除指定文件或目录"""

import os
import shutil

_LB = "<"
_RB = ">"
_A = _LB + "action"
_C = _LB + "/action" + _RB

META = {
    "type": "file_delete",
    "icon": "fa-solid fa-trash-can",
    "label": "删除文件",
    "color": "#f87171",
    "order": 60,
    "description": "删除指定文件或目录",
    "params": [{"name": "file", "required": True, "desc": "文件或目录路径"}],
    "accepts_body": False,
    "prompt": (
        "6. file_delete：删除指定文件或目录。必需参数 file。\n"
        "   示例：\n"
        + "   " + _A + ' type="file_delete" id="delete1" file="temp.txt"' + _RB + _C + "\n"
    ),
}


def _as_bool(v, default=False):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes", "on")


def _backup_dir(path):
    """删除目录前打包备份到快照目录，返回备份文件路径（失败返回 None）。"""
    try:
        import time as _t
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        snap = os.path.join(base, "service_logs", "_change_snapshots", "deleted_dirs")
        os.makedirs(snap, exist_ok=True)
        stamp = _t.strftime("%Y%m%d_%H%M%S")
        name = os.path.basename(os.path.normpath(path)) or "dir"
        out = os.path.join(snap, "%s_%s" % (name, stamp))
        shutil.make_archive(out, "zip", path)
        return out + ".zip"
    except Exception:
        return None


def run(ctx, params, body):
    file_ = params.get("file")
    if not file_:
        return {"success": False, "summary": "缺少 file 参数", "error": "缺少 file 参数",
                "feedback": "缺少 file 参数"}
    path = ctx.resolve_path(file_)
    if not os.path.exists(path):
        return {"success": False, "summary": "文件不存在",
                "error": "文件不存在: " + path,
                "feedback": "文件不存在，无法删除: " + path}
    if os.path.isdir(path):
        # 目录删除需要显式 recursive=true，避免 AI 手滑一次 rmtree 掉整个项目
        if not _as_bool(params.get("recursive"), False):
            return {"success": False, "summary": "拒绝删除目录",
                    "error": "删除目录需要 recursive=true",
                    "feedback": "检测到目标是目录，为防误删已拒绝。\n"
                                "如确需删除整个目录，请显式加参数 recursive=\"true\"。\n"
                                "路径: " + path}
        bak = _backup_dir(path)
        shutil.rmtree(path)
        note = ("\n已自动备份到: " + bak) if bak else "\n（警告：备份失败，无法恢复）"
        return {"success": True, "summary": "已删除目录",
                "feedback": "目录已删除: " + path + note,
                "info": {"path": path, "backup": bak}}
    os.remove(path)
    return {"success": True, "summary": "已删除",
            "feedback": "文件已删除: " + path, "info": {"path": path}}
