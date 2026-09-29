"""后台进程托管内核（内部模块，非技能，文件名 _ 开头以跳过技能扫描）。

职责：接管 DeepHelp 启动的所有后台/长驻进程，提供 注册 / 查询 / 停止(进程树) /
日志 tail / 存活巡检 能力。跨 skill 单例共享（经 sys.modules）。

关键设计：
- 启动时 stdout/stderr 重定向到独立日志文件，绝不留管道句柄给父进程，
  从根本上避免 subprocess 因常驻孙进程持有管道而永久阻塞。
- 进程树停止用 taskkill /T /F（Windows），避免只杀直接子进程留孤儿。
- 存活判定用 OpenProcess + GetExitCodeProcess（STILL_ACTIVE=259），可靠且轻量。
"""

import os
import sys
import time
import threading
import subprocess
import ctypes

# 运行时数据根目录：frozen 时用 exe 同级（持久可写），否则用项目根。
# 绝不能用 __file__ 上级——打包单文件模式下 __file__ 指向 _MEIPASS 临时目录，
# 程序退出时该目录会被删除，而仍持有日志句柄的服务进程会导致删除失败报错。
if getattr(sys, "frozen", False):
    _ROOT_DIR = os.path.dirname(sys.executable)
else:
    _ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.environ.get("DH_SERVICE_LOG_DIR") or os.path.join(_ROOT_DIR, "service_logs")
SERVICES_STATE_FILE = os.path.join(LOG_DIR, "services.json")
_IS_WINDOWS = os.name == "nt"

# Windows 进程创建标志
_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200

_STILL_ACTIVE = 259


def _pid_alive(pid):
    """判断 pid 是否仍存活（Windows 用 OpenProcess + GetExitCodeProcess）。"""
    if not pid or pid <= 0:
        return False
    if not _IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def _pid_create_time(pid):
    """返回进程创建时间（epoch 秒）；拿不到返回 None。
    用于识别 PID 复用：pid 存活但创建时间对不上 → 是别的进程。"""
    if not pid or pid <= 0 or not _IS_WINDOWS:
        return None
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return None
        try:
            creation = ctypes.c_ulonglong(0)
            exit_t = ctypes.c_ulonglong(0)
            kernel = ctypes.c_ulonglong(0)
            user = ctypes.c_ulonglong(0)
            if not k32.GetProcessTimes(h, ctypes.byref(creation), ctypes.byref(exit_t),
                                       ctypes.byref(kernel), ctypes.byref(user)):
                return None
            # FILETIME 是 100ns 单位，起点 1601-01-01 → 转 Unix epoch
            return creation.value / 1e7 - 11644473600
        finally:
            k32.CloseHandle(h)
    except Exception:
        return None


class ManagedProcess:
    """一条被托管的后台进程记录。"""

    def __init__(self, sid, pid, name, cmd, cwd, log_path):
        self.id = sid
        self.pid = pid
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.log_path = log_path
        self.start_time = time.time()
        self.create_time = None   # 进程真实创建时间（识别 PID 复用）

    def _alive_and_same(self):
        """存活且非 PID 复用：进程在，且其真实创建时间与本记录相符。
        create_time 未知（拿不到/未记录）时降级为只看存活。"""
        if not _pid_alive(self.pid):
            return False
        if self.create_time is None:
            return True
        ct = _pid_create_time(self.pid)
        if ct is None:
            return True   # 拿不到就信存活
        # 容差 5 秒：记录时刻与进程真实创建时刻可能有细微差
        return abs(ct - self.create_time) <= 5

    def to_dict(self):
        alive = _pid_alive(self.pid)
        reused = alive and not self._alive_and_same()   # pid 被别人占了
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "log_path": self.log_path,
            "start_time": self.start_time,
            "start_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)),
            "uptime_sec": int(time.time() - self.start_time),
            "alive": alive and not reused,
            "pid_reused": reused,
        }


class ProcessManager:
    """后台进程托管单例。"""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._init()
                    cls._instance = obj
        return cls._instance

    def _init(self):
        self._procs = {}          # id -> ManagedProcess
        self._lock = threading.RLock()
        self._seq = 0
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
        except Exception:
            pass
        self._load()

    # ── 持久化：services.json 存进程记录，程序重启后仍可见历史服务 ──
    def _load(self):
        try:
            if not os.path.isfile(SERVICES_STATE_FILE):
                return
            import json as _json
            with open(SERVICES_STATE_FILE, "r", encoding="utf-8") as f:
                data = _json.load(f)
            for rec in data.get("procs", []):
                mp = ManagedProcess(rec.get("id"), rec.get("pid"), rec.get("name"),
                                    rec.get("cmd"), rec.get("cwd"), rec.get("log_path"))
                mp.start_time = rec.get("start_time", mp.start_time)
                mp.create_time = rec.get("create_time")
                self._procs[mp.id] = mp
            self._seq = max([int(p.id[3:]) for p in self._procs.values()
                             if p.id.startswith("svc") and p.id[3:].isdigit()] + [0])
        except Exception:
            pass

    def _save(self):
        try:
            import json as _json
            with self._lock:
                recs = [{"id": mp.id, "pid": mp.pid, "name": mp.name, "cmd": mp.cmd,
                         "cwd": mp.cwd, "log_path": mp.log_path, "start_time": mp.start_time,
                         "create_time": mp.create_time}
                        for mp in self._procs.values()]
            tmp = SERVICES_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump({"procs": recs}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SERVICES_STATE_FILE)
        except Exception:
            pass

    # ── 内部：生成短 id ──
    def _next_id(self):
        with self._lock:
            self._seq += 1
            return "svc" + str(self._seq).zfill(3)

    # ── 启动托管进程 ──
    def launch(self, cmd, cwd=None, name=None, log_file=None):
        """启动后台进程并托管。返回 ManagedProcess。
        命令输出重定向到独立日志文件，立即返回、绝不阻塞。"""
        cmd = (cmd or "").strip()
        if not cmd:
            raise ValueError("命令为空")
        cwd = cwd or _ROOT_DIR
        sid = self._next_id()
        if not name:
            name = cmd.split()[0] if cmd.split() else sid
        if not log_file:
            log_file = os.path.join(LOG_DIR, sid + ".log")

        flags = 0
        if _IS_WINDOWS:
            flags = _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP

        # 关键：stdout/stderr 落文件，父进程不持有管道 → 永不因孙进程卡死
        lf = open(log_file, "a", encoding="utf-8", errors="replace")
        try:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=cwd,
                stdout=lf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
        finally:
            lf.close()

        mp = ManagedProcess(sid, proc.pid, name, cmd, cwd, log_file)
        mp.create_time = _pid_create_time(proc.pid)
        with self._lock:
            self._procs[sid] = mp
        self._save()
        return mp

    # ── 查询 ──
    def list(self):
        with self._lock:
            items = list(self._procs.values())
        return [mp.to_dict() for mp in items]

    def get(self, ident):
        """ident 可为 id 或 pid（字符串/数字）。"""
        s = str(ident).strip()
        with self._lock:
            if s in self._procs:
                return self._procs[s]
            for mp in self._procs.values():
                if str(mp.pid) == s:
                    return mp
        return None

    # ── 停止（进程树）──
    def stop(self, ident):
        mp = self.get(ident)
        if mp is None:
            return False, "未找到托管进程: " + str(ident)
        if not _pid_alive(mp.pid):
            self._save()
            return True, "进程已不在运行 (pid " + str(mp.pid) + ")"
        if _IS_WINDOWS:
            try:
                r = subprocess.run(
                    ["taskkill", "/PID", str(mp.pid), "/T", "/F"],
                    capture_output=True, text=True, timeout=15,
                    creationflags=_CREATE_NO_WINDOW,
                )
                ok = r.returncode == 0
                msg = (r.stdout or r.stderr or "").strip()
                self._save()
                return ok, msg
            except Exception as e:
                return False, "停止失败: " + str(e)
        else:
            try:
                os.kill(mp.pid, 15)
                self._save()
                return True, "已发送 SIGTERM"
            except Exception as e:
                return False, "停止失败: " + str(e)

    # ── 日志 tail ──
    def get_log(self, ident, tail=50):
        mp = self.get(ident)
        if mp is None:
            return None, "未找到托管进程: " + str(ident)
        if not os.path.isfile(mp.log_path):
            return "", None
        try:
            with open(mp.log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                block = 65536
                window = min(size, max(block, int(tail) * 400))
                f.seek(size - window)
                raw = f.read(window)
            for enc in ("utf-8", "gbk"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("utf-8", errors="replace")
            lines = text.splitlines(keepends=True)
            n = max(1, int(tail))
            return "".join(lines[-n:]), None
        except Exception as e:
            return None, "读取日志失败: " + str(e)

    # ── 巡检：清理已退出记录（保留但标记）──
    def reconcile(self):
        alive, dead = [], []
        for mp in self.list():
            (alive if mp["alive"] else dead).append(mp)
        return alive, dead


def get_manager():
    """获取 ProcessManager 单例。"""
    return ProcessManager()


__all__ = ["ProcessManager", "ManagedProcess", "get_manager", "LOG_DIR"]