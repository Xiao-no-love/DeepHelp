# 交接文档：python 动作子进程隔离（#6）

> 交接目标：把 `python` 动作从「宿主进程内 exec」改成「子进程执行」，根治超时线程泄漏 / 崩溃窗口问题。
> 交接人：上一个猫娘 AI。上下文将满，故留此文。
> 日期：2026-09-26

---

## 0. 一句话背景

`python` 动作现在跑在 **DeepHelp 宿主进程内**（与 pywebview / tkinter 同进程），
用 `exec(code, globals, globals)` 执行。后果：
- 超时**无法强杀**线程（Python 语言限制）→ 死循环线程永久泄漏；
- 危险代码（如 `import webview; webview.windows[0].destroy()`）会**崩掉整个窗口**；
- 早期曾用「正则扫描危险调用」拦截，实测**既误伤正常代码又容易被 getattr 绕过**，已废弃。

**根治方案：子进程隔离。** 崩了只死子进程，宿主安然无恙；超时直接 kill 子进程。

---

## 1. 当前代码位置（务必先读）

| 文件 | 位置 | 内容 |
|---|---|---|
| `action.py` | ~296-400 行 | `PythonExecutor` 类（核心，要改的就是这里） |
| `action.py` | ~404-415 行 | `Context` 类，`self.python_executor = _python_executor` |
| `actions/python_exec.py` | 全文 57 行 | python 动作技能，调 `ctx.python_executor.execute(body)` |
| `actions/python_reset.py` | 全文 29 行 | 调 `ctx.python_executor.reset()` |
| `config.py` | `build_system_prompt` | python 动作的 prompt 在 `python_exec.py` 的 META |

### PythonExecutor 现状（关键片段）

```python
class PythonExecutor:
    _instance = None
    _runaway = 0   # 累计超时失控次数（供排查）

    def _init(self):
        self.last_output = ""
        self.timeout = 30
        self.globals = self._build_globals()

    def _build_globals(self):
        g = {"__builtins__": __builtins__}
        g["available"] = self._available
        g["list_available"] = self._list_available
        return g

    def execute(self, code):
        stdout = io.StringIO()
        result = {"err": None, "mod_err": None}
        def _run():
            try:
                exec(code, self.globals, self.globals)
            except ModuleNotFoundError as e:
                result["mod_err"] = ...
            except BaseException as e:
                result["err"] = str(e)
        with _EXEC_LOCK:
            old = sys.stdout
            sys.stdout = stdout
            th = threading.Thread(target=_run, daemon=True)
            try:
                th.start()
                th.join(self.timeout)
                if th.is_alive():
                    PythonExecutor._runaway += 1
                    return stdout.getvalue(), "执行超时...（无法强杀线程）"
                if result["mod_err"] is not None:
                    return ..., "模块不可用：...两条出路..."
                return stdout.getvalue(), result["err"]
            finally:
                sys.stdout = old

    def reset(self):
        self.globals = self._build_globals()
```

---

## 2. ⚠️ 核心难点（下一个我必须先想清楚）

### 难点 A：打包态**没有独立的 python.exe**（最大坑）

PyInstaller 单文件模式把解释器打包进 exe，**磁盘上没有可调用的 python.exe**。
- `sys.executable` 在 frozen 态指向 **deephelp.exe 自身**，不是 python 解释器；
- `multiprocessing` 默认也用 `sys.executable`，直接套会**递归启动 exe**，死循环。

**候选方案（按推荐度）：**

1. **frozen 态：用 `sys.executable` + 特殊 argv 标记**（PyInstaller 官方支持）
   - 打包时确保 `multiprocessing.freeze_support()` 在 `main()` 最早调用；
   - 子进程用 `subprocess.Popen([sys.executable, "--py-worker"], ...)`；
   - exe 启动时判断 `--py-worker` 参数 → 进入 worker 模式（读 stdin 的 code → exec → 结果写 stdout）→ 退出；
   - **非 frozen 态**：`sys.executable` 就是真的 python.exe，直接 `[sys.executable, "-c", code]` 或 worker 脚本。
   - 优点：唯一能在打包态跑通的正路。缺点：要在 main.pyw 加 worker 分支。

2. **多进程 multiprocessing.Process**：同样依赖 `freeze_support()`，且 Windows 下 spawn 要传 code 字符串，麻烦。

3. **降级：接受无隔离，只做"防呆"** —— 如果老板不想动 main.pyw，就保留现状 + 文档说明。
   （但老板这次明确要改 #6，所以应选方案 1。）

### 难点 B：跨调用**状态共享会丢失**

现状 `self.globals` 跨多次 python 调用**共享变量**（AI 可以先定义变量，下次接着用）。
子进程方案下，每次调用是独立进程，**变量不共享**。

**候选：**
- **方案 B1（简单）**：接受失去状态共享。每次调用独立。文档/提示词里写明。
  - 影响：AI 若依赖跨调用变量会失败，但这是少数情况（多数 python 调用是独立脚本）。
- **方案 B2（复杂）**：维护一个**长驻子进程**，通过 stdin/stdout 收发 code，用 pickle 传 globals。
  - 好处：保留状态共享 + 超时可 kill（kill 后重建子进程，状态丢失）。
  - 坏处：协议复杂、编码/边界处理麻烦、子进程崩溃要能重启。
- **建议**：先上 B1（够用、简单、稳），若老板抱怨丢状态再考虑 B2。

### 难点 C：`cwd` 处理

`python_exec.py` 现在用 `os.chdir()` 切工作目录再执行。子进程方案：
- 直接把 `cwd` 传给 `subprocess.Popen(..., cwd=目标目录)`；
- 子进程内不用再 chdir，也不需要 `os.getcwd()` 恢复逻辑（子进程退出即清理）。
- 注意：`python_exec.py` 的 chdir 逻辑要相应简化。

### 难点 D：stdout / 错误捕获

- 子进程 stdout/stderr 用 `PIPE` 捕获（`communicate(timeout=...)`）；
- 超时：`communicate` 抛 `TimeoutExpired` → `kill()` 子进程树（复用 shell_exec 里的 `_kill_tree` 思路，或 `taskkill /T /F`）；
- `ModuleNotFoundError`：worker 里捕获后，把错误类型/名字回传（约定一个结果协议，如最后一行 JSON）。

### 难点 E：`available()` / `list_available()` 辅助

现在注入到 globals。子进程方案：
- 在 worker 里预设同样两个函数（worker 端注入）；
- `_BUNDLED_LIBS` 清单也要在 worker 侧可达。

---

## 3. 已做的临时缓解（本轮，别丢）

- `_EXEC_LOCK`（`action.py` ~315 行）：串行化执行，防超时残留线程与后续执行**互相覆盖 sys.stdout**。
- `_runaway` 计数：累计超时失控次数。
- 超时提示已改为**诚实文案**（明说"无法强杀线程"）。
- **废弃**了正则危险扫描（`_scan` 已删）——别再捡回来。

---

## 4. 推荐实施步骤

1. **先读**：`action.py` 296-400、`actions/python_exec.py`、`main.pyw`、`config.py` 的 build_system_prompt。
2. **决策**：向老板确认 ① 是否接受"失去跨调用状态共享"（方案 B1）；② 是否允许改 `main.pyw`（方案 A 必需）。
3. **实现 worker**：
   - 新建 `actions/_py_worker.py`（或直接在 main.pyw 加分支）：读 stdin → exec → 结果（stdout + err + mod_err）以约定格式写 stdout。
   - `main.pyw` 最前面加 `--py-worker` 分支 + `multiprocessing.freeze_support()`（若用 multiprocessing）。
   - 打包 spec 确认 worker 脚本被收进（datas 或 hiddenimports）。
4. **改 PythonExecutor.execute**：subprocess 调 worker，带 timeout，超时 kill 进程树。
5. **改 python_exec.py**：cwd 传子进程，去掉 chdir。
6. **改 python_reset.py**：子进程方案下 reset 无意义（每次独立）→ 改为提示或空操作。
7. **更新提示词**：说明 python 动作现在独立执行、无跨调用状态；`available()` 仍可用。
8. **测试**（见下）。

---

## 5. 测试要点（务必覆盖）

- [ ] 普通脚本：`print(1+1)` → 输出 2。
- [ ] **死循环**：`while True: pass` → 超时后**子进程被杀**，宿主正常，无泄漏线程。
- [ ] **崩溃代码**：`import webview; webview.windows[0].destroy()` → 子进程崩，**窗口无恙**（这是 #6 的核心验收点）。
- [ ] **缺库**：`import 不存在` → 给可行动提示。
- [ ] `available('json')` / `available('numpy')` → True / False。
- [ ] `cwd` 参数：在指定目录创建文件，确认落在该目录。
- [ ] 打包态（frozen）：**这是重点**，必须重新打包后在 exe 上测一遍 worker 分支能跑。
- [ ] 多次连续调用：确认无句柄泄漏、无进程堆积（任务管理器看）。

---

## 6. 工具/环境注意事项（本轮踩过的坑）

1. **`file_read`/`python` 读源码会解码 HTML 实体**：字面量 `&` 会被工具层解码成 `&` 显示。要拿磁盘真实字节，用 python 读 `rb`，并按 `chr(38)` 拼实体名计数。判断 `esc()` 是否真转义时靠这个。
2. **`replace_lines` 行号易漂移**：改一处后行号变，后续段会锚点失败。改前先 python 打印实际行号；多段用一次调用带多个 `@@` 段。
3. **改完立即 `ast.parse` + `node --check`**。
4. **本机 python 是 3.11**，路径 `C:\Users\xiao\AppData\Local\Programs\Python\Python311`。
5. **不要启动任何程序**（老板明确要求，只改代码 + 静态校验）。
6. **备份**：`F:\DeepHelp\UPdate\optimize_backup_<时间戳>`（改前必备份）。

---

## 7. 项目其它已知遗留（非 #6，供参考）

- **`_change_tracker` 快照只增不减**：仅 `clear()` 手动清，长会话堆积。（`actions/_change_tracker.py`）
- **`api.py` 是 915 行上帝对象**：桥接/对话循环/配置/窗口/文件预览/服务管理全塞一起。
- **前后端靠 `_js("函数名(" + json + ")")` 拼字符串通信**：天生脆弱（esc 已修，但架构没变）。
- **强依赖 DeepSeek 网页 DOM**（`.ds-button--primary`、SVG path 硬编码）：对方改版即失灵。
- **`_do_connect` 里 `time.sleep(0.5)`** 阻塞 worker 线程。

---

## 8. 本轮（2026-09-26）已完成的修复（15 文件，别重复做）

1. main.pyw 单实例锁：CreateMutexW 前 SetLastError(0)
2. api.py 动作链计数移到内层每轮重置，删死变量
3. action.py 审计日志轮转改二进制 seek
4. _process_manager 加 _pid_create_time 识别 PID 复用
5. action.py _finish 调用点过滤 success/summary/error 键
6. shell_exec 前台超时改 Popen+communicate+taskkill /T
7. dir_list/file_read getsize 加保护
8. config.py 删死代码 ACTION_META
9. api.py watchdog 每轮重读 action_timeout
10. api.py _worker_loop 异常写审计
（python 的 _EXEC_LOCK + 诚实提示是本轮做的临时缓解，见第 3 节）

---

## 9. 参考：本轮所有改动文件

M action.py / actions/_change_tracker.py / actions/_process_manager.py /
actions/dir_list.py / actions/file_append.py / actions/file_delete.py /
actions/file_read.py / actions/file_write.py / actions/replace_lines.py /
actions/shell_exec.py / actions/smart_patch.py / api.py / config.py /
main.pyw / webui/js/app.js

（git status 可见；未提交。改前备份在 optimize_backup_20260926_1346）