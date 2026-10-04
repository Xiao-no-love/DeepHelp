
"""
DeepHelp — 动作解析与执行内核（模块化版）
技能 = actions/ 下一个 .py（自带 META + run）；加技能 = 丢文件，内核零改
对外兼容旧接口：parse_actions / strip_actions / execute_action / get_param_bool
"""

import os
import io
import re
import sys
import time
import json
import subprocess
import importlib.util
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# 以下为 actions/ 目录各技能用到的第三方依赖，此处静态导入仅供 PyInstaller 扫描收集。
# actions/*.py 是运行时动态加载的，PyInstaller 静态分析看不到其中的 import，故在此统一声明。
import whatthepatch  # noqa: F401  (actions/smart_patch.py 依赖)

_LB = "<"
_RB = ">"
_AMP = chr(38)
_SEMI = chr(59)
_OPEN = _LB + "action"
_CLOSE = _LB + "/action" + _RB

# 运行时数据目录：frozen 时为 exe 所在目录（可写、持久），否则为源码目录。
if getattr(sys, "frozen", False):
    _RUNTIME_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", _RUNTIME_DIR)
else:
    _RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _RUNTIME_DIR

# 技能目录：优先用 exe 同级的外部 actions/（用户可增删技能），
# 否则回退到打包进 exe 的 actions/（_MEIPASS）。
_external_actions = os.path.join(_RUNTIME_DIR, "actions")
ACTIONS_DIR = _external_actions if os.path.isdir(_external_actions) else os.path.join(_BUNDLE_DIR, "actions")
AUDIT_LOG_PATH = os.path.join(_RUNTIME_DIR, "audit.log")
DEFAULT_MAX_READ_CHARS = 10000
DEFAULT_SHELL_TIMEOUT = 30
_RESERVED_ATTRS = {"type", "id", "replay"}


def _ent(name):
    return _AMP + name + _SEMI


_ENT_LT = _ent("lt")
_ENT_GT = _ent("gt")
_ENT_AMP = _ent("amp")
_ENT_QUOT = _ent("quot")
_ENT_APOS = _ent("apos")


# ========== XML 实体反转义 ==========
_XML_ESCAPE = {"&": _ENT_AMP, "<": _ENT_LT, ">": _ENT_GT, '"': _ENT_QUOT, "'": _ENT_APOS}
_UNESCAPE_TABLE = {v: k for k, v in _XML_ESCAPE.items()}
_UNESCAPE_RE = re.compile("|".join(re.escape(e) for e in _UNESCAPE_TABLE))


def unescape_xml(text: str) -> str:
    return _UNESCAPE_RE.sub(lambda m: _UNESCAPE_TABLE[m.group()], text)


# ========== 解析器 ==========
def _scan_header_end(text: str, start: int) -> int:
    i = start
    n = len(text)
    q = None
    while i < n:
        c = text[i]
        if q is None:
            if c in ('"', "'"):
                q = c
            elif c == _RB:
                return i
        elif c == q:
            q = None
        i += 1
    return -1


_ATTR_RE = re.compile(r"""([A-Za-z_][\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def _parse_attrs(header: str) -> Dict[str, str]:
    out = {}
    for m in _ATTR_RE.finditer(header):
        k = m.group(1)
        v = m.group(2)
        if v is None:
            v = m.group(3)
        if v is None:
            v = m.group(4)
        out[k] = unescape_xml(v)
    return out
# ---- 动作类型归一化（容错：type/name 混用、拼写/大小写差异）----
_TYPE_ALIAS_KEYS = ("type", "Type", "TYPE", "typ", "ty")


def _all_known_types():
    try:
        return list(get_registry().keys())
    except Exception:
        return []


def _normalize_type_value(raw, known):
    """把 raw 归一化为 known 里的规范名；无法确定返回 None。known 为空则宽松放行。"""
    if not raw:
        return None
    raw = str(raw).strip()
    if not known:
        return raw
    if raw in known:
        return raw
    low = raw.lower()
    for k in known:
        if k.lower() == low:
            return k
    norm = low.replace("-", "_")
    for k in known:
        if k.lower().replace("-", "_") == norm:
            return k
    import difflib
    m = difflib.get_close_matches(low, [k.lower() for k in known], n=1, cutoff=0.8)
    if m:
        for k in known:
            if k.lower() == m[0]:
                return k
    return None


def _suggest_type(raw):
    """给一个拼错/记错的类型名找最接近的已注册类型，找不到返回空串。"""
    known = _all_known_types()
    if not known or not raw:
        return ""
    import difflib
    m = difflib.get_close_matches(str(raw).lower(), [k.lower() for k in known], n=1, cutoff=0.6)
    if m:
        for k in known:
            if k.lower() == m[0]:
                return k
    return ""


def _resolve_type(attrs):
    """从属性里解析动作类型，返回 (规范type 或 None, 诊断/容错提示 或 None)。
    第一轮认 type 系键（允许大小写/拼写模糊）；第二轮才用 name/action 兜底（仅精确匹配，
    避免把普通同名参数误当类型）。"""
    for key in _TYPE_ALIAS_KEYS:
        v = attrs.get(key)
        if v:
            known = _all_known_types()
            norm = _normalize_type_value(v, known)
            if norm is None:
                sug = _suggest_type(v)
                msg = "属性 " + key + '="' + str(v) + '" 不是已知动作类型'
                if sug:
                    msg += "，你是不是想用 " + sug + " ？"
                return None, msg
            if key != "type" or norm != v:
                return norm, "属性 " + key + '="' + str(v) + '" 已容错识别为 type="' + norm + '"'
            return norm, None
    for key in ("name", "action"):
        v = attrs.get(key)
        if v and v in _all_known_types():
            return v, "属性 " + key + '="' + str(v) + '" 已容错识别为 type（建议写成 type）'
    return None, None
def _find_close(text: str, start: int) -> int:
    i = start
    n = len(text)
    depth = 1
    olen = len(_OPEN)
    clen = len(_CLOSE)
    while i < n:
        if text.startswith(_CLOSE, i):
            depth -= 1
            if depth == 0:
                return i
            i += clen
            continue
        if text.startswith(_OPEN, i):
            after = i + olen
            if after < n and (text[after].isspace() or text[after] == _RB):
                depth += 1
                i += olen
                continue
        i += 1
    return -1


def parse_actions(text: str) -> List[Tuple[str, Optional[str], str, str]]:
    res = []
    pos = 0
    n = len(text)
    olen = len(_OPEN)
    clen = len(_CLOSE)
    while pos < n:
        start = text.find(_OPEN, pos)
        if start == -1:
            break
        after = start + olen
        if after < n and not (text[after].isspace() or text[after] == _RB):
            pos = start + 1
            continue
        he = _scan_header_end(text, after)
        if he == -1:
            pos = start + 1
            continue
        attrs = _parse_attrs(text[after:he])
        t, _tw = _resolve_type(attrs)
        if t is None:
            if _tw:
                _audit_log("(malformed)", attrs.get("id"), text[after:he], _tw, False, 0)
            pos = he + 1
            continue
        ci = _find_close(text, he + 1)
        if ci == -1:
            pos = he + 1
            continue

        raw_body = text[he + 1:ci]
        if raw_body.startswith("\r\n"):
            raw_body = raw_body[2:]
        elif raw_body.startswith("\n"):
            raw_body = raw_body[1:]
        if raw_body.endswith("\r\n"):
            raw_body = raw_body[:-2]
        elif raw_body.endswith("\n"):
            raw_body = raw_body[:-1]
        body = unescape_xml(raw_body)
        res.append((t, attrs.get("id"), text[after:he], body))
        pos = ci + clen
    return res


def strip_actions(text: str) -> str:
    out = []
    pos = 0
    n = len(text)
    olen = len(_OPEN)
    clen = len(_CLOSE)
    while pos < n:
        start = text.find(_OPEN, pos)
        if start == -1:
            out.append(text[pos:])
            break
        after = start + olen
        if after < n and not (text[after].isspace() or text[after] == _RB):
            out.append(text[pos:start + olen])
            pos = start + olen
            continue
        he = _scan_header_end(text, after)
        if he == -1:
            out.append(text[pos:])
            break
        ci = _find_close(text, he + 1)
        if ci == -1:
            out.append(text[pos:])
            break
        out.append(text[pos:start])
        pos = ci + clen
    return "".join(out).strip()
def parse_segments(text: str) -> List[Tuple[str, Any]]:
    """按出现顺序把回复切成「文本段 / 动作段」，供前端按原文顺序交错展示。
    返回 list，元素为 ('text', 文本) 或 ('action', (type, id, params, body))。"""
    segs = []
    pos = 0
    n = len(text)
    olen = len(_OPEN)
    clen = len(_CLOSE)
    while pos < n:
        start = text.find(_OPEN, pos)
        if start == -1:
            segs.append(("text", text[pos:]))
            break
        after = start + olen
        if after < n and not (text[after].isspace() or text[after] == _RB):
            segs.append(("text", text[pos:after]))
            pos = after
            continue
        he = _scan_header_end(text, after)
        if he == -1:
            segs.append(("text", text[pos:]))
            break
        attrs = _parse_attrs(text[after:he])
        t, _tw = _resolve_type(attrs)
        if t is None:
            if _tw:
                _ci = _find_close(text, he + 1)
                segs.append(("text", text[pos:start] + "⚠️ 动作未执行：" + _tw))
                pos = (_ci + clen) if _ci != -1 else (he + 1)
            else:
                segs.append(("text", text[pos:he + 1]))
                pos = he + 1
            continue
        ci = _find_close(text, he + 1)
        if ci == -1:
            segs.append(("text", text[pos:]))
            break
        segs.append(("text", text[pos:start]))
        raw_body = text[he + 1:ci]
        if raw_body.startswith("\r\n"):
            raw_body = raw_body[2:]
        elif raw_body.startswith("\n"):
            raw_body = raw_body[1:]
        if raw_body.endswith("\r\n"):
            raw_body = raw_body[:-2]
        elif raw_body.endswith("\n"):
            raw_body = raw_body[:-1]
        body = unescape_xml(raw_body)
        segs.append(("action", (t, attrs.get("id"), text[after:he], body)))
        pos = ci + clen
    return segs

# ========== 参数解析 ==========
def get_param(params_str: str, key: str) -> Optional[str]:
    if params_str is None:
        return None
    return _parse_attrs(params_str).get(key)


def get_param_int(params_str: str, key: str, default: int) -> int:
    val = get_param(params_str, key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_param_bool(params_str: str, key: str, default: bool = False) -> bool:
    val = get_param(params_str, key)
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes", "on")


# ========== 审计 ==========
_AUDIT_MAX_BYTES = 5 * 1024 * 1024  # 单文件上限 5MB，超过则截断保留后半


def _audit_log(action_type, action_id, params, result, success, duration_ms):
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type, "id": action_id, "params": params,
            "result": (result or "")[:500], "success": success,
            "duration_ms": duration_ms,
        }
        # 日志轮转：超过上限时只保留后半，避免 audit.log 无限膨胀
        try:
            if os.path.exists(AUDIT_LOG_PATH) and os.path.getsize(AUDIT_LOG_PATH) > _AUDIT_MAX_BYTES:
                # 用二进制 seek（字节偏移），文本模式 seek 传字节数可能抛异常导致轮转失效
                size = os.path.getsize(AUDIT_LOG_PATH)
                with open(AUDIT_LOG_PATH, "rb") as f:
                    f.seek(max(0, size - _AUDIT_MAX_BYTES // 2))
                    tail = f.read()
                with open(AUDIT_LOG_PATH, "wb") as f:
                    f.write(tail)
        except Exception:
            pass
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ========== Python 执行器 ==========
# 说明：python 动作在宿主进程内 exec（与 pywebview/tkinter 同进程）。因此：
#   - 不做"正则危险扫描拦截"（实测既误伤正常代码、又能被 getattr 轻易绕过，是安全剧场）。
#   - 改为：① 精确捕获 ModuleNotFoundError，给出可行动提示；② 执行加超时兜底；
#   - 注入 available()/list_available() 辅助，让 AI 先查库再用，避免试错。
import re as _re
import threading as _threading
import importlib as _importlib

# 打包环境显式带入的基础库（与 deephelp.spec 的 hiddenimports 保持一致）。
# 仅用于向 AI 说明"哪些库无需试错即可用"，非硬约束。
_BUNDLED_LIBS = ["json", "os", "sys", "re", "time", "datetime", "math", "random",
                 "collections", "itertools", "functools", "pathlib", "glob",
                 "hashlib", "base64", "csv", "io", "subprocess", "shutil", "tempfile",
                 "urllib", "http", "socket", "threading", "queue", "traceback",
                 "requests", "bs4", "yaml", "dateutil", "psutil", "pyperclip",
                 "whatthepatch", "prompt"]

# 串行化 python 执行：防止超时残留线程与后续执行互相覆盖 sys.stdout
_EXEC_LOCK = _threading.Lock()


class PythonExecutor:
    _instance = None
    _runaway = 0   # 累计超时失控次数（供排查）

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.last_output = ""
        self.timeout = 30  # 秒；可由 config 覆盖
        self.globals = self._build_globals()

    def _build_globals(self):
        g = {"__builtins__": __builtins__}
        # 注入库可用性辅助（无害，供 AI 先查后用）
        g["available"] = self._available
        g["list_available"] = self._list_available
        return g

    @staticmethod
    def _available(module_name):
        """判断某模块在当前运行环境是否可导入（不实际导入）。"""
        try:
            spec = _importlib.util.find_spec(str(module_name))
            return spec is not None
        except Exception:
            return False

    @staticmethod
    def _list_available():
        """返回打包显式带入的基础库清单。"""
        return list(_BUNDLED_LIBS)

    def execute(self, code: str) -> Tuple[str, Optional[str]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        result = {"err": None, "mod_err": None}

        def _run():
            try:
                exec(code, self.globals, self.globals)
            except ModuleNotFoundError as e:
                result["mod_err"] = getattr(e, "name", None) or str(e)
            except BaseException as e:  # 含 SystemExit 等，避免拖垮宿主
                result["err"] = str(e)

        def _merge(out: str) -> str:
            se = stderr.getvalue()
            if se:
                if out and not out.endswith("\n"):
                    out += "\n"
                out += "[stderr]\n" + se
            return out

        # 串行化执行：sys.stdout 是进程全局的，若上一个超时线程仍在跑，
        # 不加锁会导致两个执行互相覆盖 stdout。加锁至少保证不串台。
        with _EXEC_LOCK:
            old, olde = sys.stdout, sys.stderr
            sys.stdout = stdout
            sys.stderr = stderr
            th = _threading.Thread(target=_run, daemon=True)
            try:
                th.start()
                th.join(self.timeout)
                if th.is_alive():
                    # 注意：Python 无法强杀线程，这是语言限制。失控线程会继续在后台运行。
                    PythonExecutor._runaway += 1
                    return _merge(stdout.getvalue()), (
                        "执行超时（>" + str(self.timeout) + "s），已放弃等待。\n"
                        "⚠️ 代码可能仍在后台运行（Python 无法强杀线程）。若反复出现，"
                        "请用 python_reset 重置环境，或检查是否有死循环 / 阻塞调用。")
                if result["mod_err"] is not None:
                    m = result["mod_err"]
                    return _merge(stdout.getvalue()), (
                        "模块不可用：`" + m + "` 不在当前运行环境（打包 exe 仅含基础库清单）。\n"
                        "可用的库：requests / bs4 / yaml / dateutil / psutil / pyperclip 及标准库。\n"
                        "两条出路：\n"
                        "  ① 改用 shell 动作调用系统 Python 执行该脚本（系统环境库更全）；\n"
                        "  ② 让老板把该库加入 deephelp.spec 的 hiddenimports 后重新打包。\n"
                        "提示：执行前可用 available('模块名') 先探测是否可用，避免试错。")
                return _merge(stdout.getvalue()), result["err"]
            finally:
                sys.stdout = old
                sys.stderr = olde

    def reset(self):
        self.globals = self._build_globals()
        self.last_output = ""


_python_executor = PythonExecutor()


# ========== 上下文 ==========
class Context:
    def __init__(self, work_dir: str = None, shell_timeout: int = DEFAULT_SHELL_TIMEOUT):
        self.work_dir = work_dir or os.getcwd()
        self.shell_timeout = shell_timeout
        self.python_executor = _python_executor

    def resolve_path(self, p: str) -> str:
        if not p:
            return os.path.normpath(self.work_dir)
        if os.path.isabs(p):
            return os.path.normpath(p)
        return os.path.normpath(os.path.join(self.work_dir, p))

    @staticmethod
    def format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @staticmethod
    def audit(*a, **kw):
        _audit_log(*a, **kw)


# ========== 注册表 ==========
def load_actions(directory: str = None) -> Tuple[Dict, List]:
    d = directory or ACTIONS_DIR
    registry = {}
    errors = []
    if not os.path.isdir(d):
        return registry, [("(dir)", "目录不存在: " + d)]
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        # 排除备份/临时文件：只认单点名的 .py（如 x.py），挡掉 x.py.bak / x.orig.py 等
        _lower = fname.lower()
        if fname.count(".") != 1 or _lower.endswith((".py.bak", ".bak", ".orig", ".tmp", ".swp")):
            continue
        fpath = os.path.join(d, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            meta = getattr(mod, "META", None)
            run = getattr(mod, "run", None)
            if meta is None:
                errors.append((fname, "缺少 META"))
                continue
            if run is None:
                errors.append((fname, "缺少 run"))
                continue
            t = meta.get("type")
            if not t:
                errors.append((fname, "META 缺少 type"))
                continue
            if t in registry:
                errors.append((fname, "type 重复: " + t))
                continue
            for _p in (meta.get("params") or []):
                _pn = _p.get("name") if isinstance(_p, dict) else None
                if _pn in _RESERVED_ATTRS:
                    errors.append((fname, "警告: 参数名 '" + str(_pn) + "' 与动作标签保留属性冲突，调用时会被标签属性覆盖，建议改名（如 service/target）"))
            registry[t] = {"meta": meta, "run": run, "file": fname}
        except Exception as e:
            errors.append((fname, "加载失败: " + str(e)))
    return registry, errors


_registry_cache = None


def get_registry() -> Dict:
    global _registry_cache
    if _registry_cache is None:
        _registry_cache, _ = load_actions()
    return _registry_cache


def reload_registry() -> Tuple[Dict, List]:
    global _registry_cache
    _registry_cache, errs = load_actions()
    return _registry_cache, errs


# ========== Prompt 拼装 ==========
_C = _LB + "/action" + _RB
_A = _LB + "action"

_PROTOCOL_HEAD = (
    "当你需要执行操作时，必须严格遵循使用如下完整的XML闭合标签形式包裹动作，"
    "系统会自动解析并返回执行结果：\n"
    + _A + ' type="动作类型" id="唯一标识符" 参数="值"' + _RB + "\n"
    + "动作内容或代码\n"
    + _C + "\n"
    + "【可用动作类型及参数说明】\n"
)

_PROTOCOL_TAIL = (
    "【action 的 replay 属性（默认 true）】\n"
    "每个 action 标签可携带可选属性 replay，用于控制该 action 的执行结果是否返回给你：\n"
    + "  · " + 'replay="true"' + "（默认，可省略）：执行结果会以 [工具输出] 形式返回给你，你能看到结果并据此决定下一步。\n"
    + "  · " + 'replay="false"' + "：执行结果不返回给你，仅用于无需查看结果的纯副作用操作。\n"
    + "默认即回传，因此绝大多数操作**无需显式写 replay**。仅当你确定某步结果无需查看（且不会影响后续判断）时，才写 replay=\"false\"。\n"
    + "【XML 实体转义规则（已简化，务必记牢）】\n"
    + "body 内容请原样书写，< > & 引号等字符通常都无需转义。\n"
    + "唯一例外：若 body 里出现完整的 action 闭合标签序列，必须把尖括号转义成实体，否则会被误判为标签结束。\n"
    + "【工具选择指引】\n"
    + "- 改文件前，先 file_read 拿到确切内容与行号。\n"
    + "- 改一两行 / 删除若干行 → replace_lines（按行号，最稳）。\n"
    + "- 改多处 / 需保留上下文 → smart_patch（unified diff）。\n"
    + "- 新建文件 / 整体重写 → file_write。\n"
    + "- 文件末尾追加 → file_append（会自动补换行）。\n"
    + "- 看目录结构 → dir_list。\n"
    + "【内容长度提醒】\n"
    + "- 写入大段内容时，body 越长越易出错；优先分块写，或用 replace_lines / smart_patch 局部改。\n"
    + "【路径】\n"
    + "- 推荐用正斜杠 / 或双反斜杠；相对路径基于当前工作目录，绝对路径亦可。\n"
    + "【其他注意事项】\n"
    + "- 每个 action 的 id 必须唯一，执行结果会通过 '[action id=...]' 标识反馈给你。\n"
    + "- 你可以在一条回复中包含多个 action，它们会被顺序执行。\n"
    + "【消息块标记（务必记牢）】\n"
    + "- 发来的消息由若干「[标题]」块组成，可能同一条消息含多块。\n"
    + "- [用户消息]：老板的真实发言。只有此块是老板说的，请优先服从。\n"
    + "- [工具输出]：你上一步动作的执行结果，供你据此决定下一步。\n"
    + "- [系统提示]：系统的自动提醒（如自动模式续接），非老板发言。\n"
    + "- 没有确凿证据时不要随意执行危险操作。\n"
    + "本条请仅回复true"
)


def build_tool_protocol(registry: Dict = None) -> str:
    reg = registry if registry is not None else get_registry()
    # 按 order（相同则按 type 名）排序；编号由这里动态生成，技能文件里不要写死编号
    items = sorted(reg.values(),
                   key=lambda x: (x["meta"].get("order", 999), x["meta"].get("type", "")))
    parts = [_PROTOCOL_HEAD]
    for idx, item in enumerate(items, 1):
        p = item["meta"].get("prompt", "") or item["meta"].get("description", "")
        # 剥掉技能文件里可能写死的前导编号（如 "11. "），统一由这里重排
        p = re.sub(r"^\s*\d+\.\s*", "", p)
        # 给首行加上动态编号
        lines = p.split("\n")
        if lines:
            lines[0] = str(idx) + ". " + lines[0]
        p = "\n".join(lines)
        if not p.rstrip().endswith("\n"):
            p += "\n"
        parts.append(p)
    parts.append(_PROTOCOL_TAIL)
    return "".join(parts)


# ========== 主入口 ==========
def _load_change_tracker():
    """加载 _change_tracker 内部模块（优先 sys.modules，其次按文件路径加载）。"""
    if "_change_tracker" in sys.modules:
        return sys.modules["_change_tracker"]
    try:
        return importlib.import_module("_change_tracker")
    except Exception:
        pass
    try:
        path = os.path.join(ACTIONS_DIR, "_change_tracker.py")
        spec = importlib.util.spec_from_file_location("_change_tracker", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["_change_tracker"] = mod
        return mod
    except Exception:
        return None


def execute_action(
    type_: str,
    id_: Optional[str],
    params: str,
    body: str,
    shell_timeout: int = DEFAULT_SHELL_TIMEOUT,
    work_dir: Optional[str] = None,
    action_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    reg = get_registry()
    item = reg.get(type_)
    meta = item["meta"] if item else {}
    icon = meta.get("icon", "?")
    label = meta.get("label", type_)
    color = meta.get("color", "#8b949e")
    if action_meta and type_ in action_meta:
        am = action_meta[type_]
        try:
            icon, label, color = am[0], am[1], am[2]
        except Exception:
            pass

    info = {
        "type": type_, "id": id_, "icon": icon, "label": label, "color": color,
        "success": False, "duration_ms": 0, "summary": "", "error": None,
        "timestamp": datetime.now().isoformat(),
    }
    t0 = time.time()

    def _finish(success, summary="", error=None, **kw):
        info["success"] = success
        info["summary"] = summary
        info["error"] = error
        info["duration_ms"] = int((time.time() - t0) * 1000)
        info.update(kw)
        # 输入全存（属性参数 + body）
        info["input"] = (params or "") + (("\n" + body) if body else "")
        # 统一文件字段（各 action 有用 path 或 file）
        files = []
        for _k in ("path", "file", "file_path"):
            _v = info.get(_k)
            if _v and _v not in files:
                files.append(_v)
        info["files"] = files

    if not item:
        _sug = _suggest_type(type_)
        _hint = ("，你是不是想用 " + _sug + " ？") if _sug else ""
        _finish(False, "未知动作类型", "未知类型: " + type_ + _hint)
        fb = '[action id="' + str(id_) + '"] 未知的动作类型: ' + type_ + _hint
        _audit_log(type_, id_, params, fb, False, info["duration_ms"])
        return False, fb, info

    pdict = _parse_attrs(params or "")
    ctx = Context(work_dir=work_dir, shell_timeout=shell_timeout)

    # 变更追踪：文件类动作执行前拍快照
    _tracker = _load_change_tracker()
    _trk_snap = None
    _trk_abs = ""
    if _tracker is not None:
        _raw = pdict.get("file") or pdict.get("path") or pdict.get("file_path")
        if _raw:
            try:
                _trk_abs = ctx.resolve_path(_raw)
                _trk_snap = _tracker.get_tracker().before(type_, _trk_abs)
            except Exception:
                _trk_snap = None
    try:
        result = item["run"](ctx, pdict, body)
        if not isinstance(result, dict):
            result = {"success": False, "summary": "返回值非 dict", "error": None,
                      "feedback": "技能返回格式错误"}
        success = bool(result.get("success"))
        fb_body = result.get("feedback", result.get("summary", ""))
        _info = dict(result.get("info", {}) or {})
        for _k in ("success", "summary", "error"):
            _info.pop(_k, None)   # 避免与位置参数冲突导致 TypeError
        _finish(success, result.get("summary", ""), result.get("error"), **_info)
        fb = '[action id="' + str(id_) + '"] ' + fb_body
        _audit_log(type_, id_, params, fb, success, info["duration_ms"])
        if _tracker is not None and _trk_snap is not None:
            try:
                _tracker.get_tracker().after(type_, _trk_abs, _trk_snap, success)
            except Exception:
                pass
        return success, fb, info
    except subprocess.TimeoutExpired as e:
        _finish(False, "超时", "执行超时 (" + str(e.timeout) + "s)")
        fb = '[action id="' + str(id_) + '"] 执行超时'
        _audit_log(type_, id_, params, fb, False, info["duration_ms"])
        return False, fb, info
    except Exception as e:
        _finish(False, "执行异常", str(e))
        fb = '[action id="' + str(id_) + '"] 执行异常: ' + str(e)
        _audit_log(type_, id_, params, fb, False, info["duration_ms"])
        return False, fb, info


__all__ = [
    "parse_actions", "strip_actions", "parse_segments", "get_param", "get_param_int", "get_param_bool",
    "execute_action", "Context", "PythonExecutor", "_python_executor",
    "load_actions", "get_registry", "reload_registry", "build_tool_protocol",
    "unescape_xml", "ACTIONS_DIR", "AUDIT_LOG_PATH",
    "DEFAULT_MAX_READ_CHARS", "DEFAULT_SHELL_TIMEOUT",
]
