# DeepHelp 执行器优化台账

> 目标：长驻服务可管理 + 执行过程可见 + 队列不阻塞
> 约定：每完成一项 `[x]`；全部完成后统一回归检查；改的是运行中程序本体，需重启 DeepHelp 生效。

## S1 进程管理地基（低风险，先做）
- [x] 1.1 新建 `actions/_process_manager.py`：ProcessManager 单例（注册/查询/kill 进程树/日志 tail/存活巡检）— 实测通过
- [x] 1.2 扩展 `actions/shell_exec.py`：新增 `background`/`name` 参数 + 超时/异常兜底 + stdin=DEVNULL
- [x] 1.3 新增动作 `actions/service_list.py`：列出在管后台服务
- [x] 1.4 新增动作 `actions/service_stop.py`：按 id/pid 停止服务（含子进程树）
- [x] 1.5 新增动作 `actions/service_log.py`：tail 服务日志
- [x] 1.6 `config.py`：补充 `services` 段（log_dir/reconcile_interval）+ 三个 service 图标；`_process_manager` 支持 DH_SERVICE_LOG_DIR 环境变量覆盖

## S2 前端「本地服务」面板（中风险）
- [x] 2.1 `webui/demo.html`：新增「服务」页签/面板容器（panel-services）
- [x] 2.2 `webui/js/app.js`：服务卡片渲染 + 停止/日志交互 + 三面板互斥 + 事件分发
- [x] 2.3 `webui/css/main.css`：服务卡片 + 存活指示灯样式
- [x] 2.4 `api.py`：暴露 list_services / stop_service / service_log 给前端

## S3 执行过程可见（中风险）
- [x] 3.1 前端三阶段：addActionStart / addActionProgress / addActionEnd（app.js）
- [x] 3.2 `api.py`：动作执行前推 start、完成后推 end（含 id/type/path）
- [x] 3.3 流式可见：长驻服务经 background+service_log 实时查看；前台 shell 因 pywebview 线程约束不做逐行流式（规避崩溃）

## S4 worker 隔离 + 看门狗（高风险，最后做）
- [x] 4.1 `api.py`：任务追踪字段 _current_task + _task_lock（保持单 worker，尊重 pywebview 线程约束）
- [x] 4.2 `api.py`：独立守护线程看门狗，长任务超时写审计日志 + 蜂鸣提醒（不碰 webview，安全）

## 最终回归检查
- [x] F1 全量 `py_compile` 语法检查（23 个 .py 全 OK）
- [x] F2 现有动作接口兼容性核对（execute_action 签名/返回结构未破坏）
- [x] F3 前端资源引用完整性（资源无缺失，24 个 api 调用全有定义）
- [x] F4 汇总变更，通知老板（含「需重启生效」提醒）

---
## 变更记录
- 2026-09-20 14:41 / actions/_process_manager.py / 新建 ProcessManager 单例，launch/list/get/stop(进程树)/get_log/reconcile，实测通过
- 2026-09-20 14:44 / actions/shell_exec.py / 新增 background/name；background 走 ProcessManager 托管；前台加 TimeoutExpired/Exception 兜底与 stdin=DEVNULL，py_compile OK
- 2026-09-20 14:47 / actions/service_list.py, service_stop.py, service_log.py / 新增三个 service 技能，py_compile 全 OK，list/log 冒烟通过
- 2026-09-20 14:52 / config.py, actions/_process_manager.py / DEFAULT_CONFIG 增 services 段与 3 个 service 图标；LOG_DIR 支持环境变量覆盖；py_compile OK，config 加载验证通过
- 2026-09-20 14:55 / 【重要发现】当前运行的是 PyInstaller 打包的 exe，其 ACTIONS_DIR 指向 _MEIPASS 临时目录，**不读源码目录**。故本次所有改动需「重新打包 exe」或「用源码直接运行」才生效。验证改为按文件路径直接加载源码。
- 2026-09-20 14:58 / 【S1 完成】端到端集成测试通过：shell background 启动→service_list 可见→service_log 读日志→service_stop 杀进程树→状态变已退出。S1 全部 6 项完结。
- 2026-09-20 15:05 / api.py / 新增 list_services / stop_service / service_log 三个桥接方法（_get_pm 兼容源码+打包），py_compile OK
- 2026-09-20 15:12 / webui/demo.html + webui/js/app.js / 新增 panel-services 面板；app.js 增 loadServices/svcStop/svcLog + 三面板互斥 + 事件分发 + 启动加载 + 5s 轮询刷新；node --check OK
- 2026-09-20 15:16 / webui/css/main.css / 追加服务卡片样式（svc-card/dot/name/pid/cmd/uptime/btns/log + 脉冲动画）
- 2026-09-20 15:22 / webui/js/app.js + api.py / 动作三阶段：执行前 addActionStart 渲染"运行中"卡片（含计时），完成 addActionEnd 定稿；app.js node --check OK，api.py py_compile OK
- 2026-09-20 15:30 / api.py / S4 务实版：worker 增 _current_task/_task_lock 追踪；新增 _start_watchdog 独立守护线程（超 action_timeout 写 watchdog 审计 + 蜂鸣）；保持单 worker 不违反 pywebview evaluate_js 线程约束；py_compile OK
- 2026-09-20 15:40 / 【全部完成】F1 全量 py_compile 23/23 OK；F2 execute_action 签名与返回三元组兼容；F3 前端资源+api 调用完整；F4 端到端：源码目录 16 技能注册、协议含 service_*/background、service 全链路通过。
- 【重要】本次改动均在 F:\DeepHelp\UPdate\optimize 源码目录；当前运行的是打包 exe（读 _MEIPASS），需重新打包或用源码运行才生效。
- 2026-09-20 15:55 / 【定界符统一】action.py + actions/*.py 共17个文件，_LB/_RB 从 ⟪⟫ 改为 <>，对齐 exe 版；协议头/尾措辞对齐（含 XML 转义规则）。py_compile 全绿，源码版解析验证通过。
- 2026-09-20 16:05 / 【bug修复】① service_stop.py/service_log.py 参数 id→service（id 与动作自身 id 冲突）；② _process_manager.get_log 增 gbk 回退（原只读 utf-8 导致中文日志乱码）。实测通过。
- 【待办】ProcessManager 服务记录仅内存态，模块重载/程序重启会丢失，考虑持久化到 json。
---
## 右侧栏重定位为「AI 操作台」（2026-09-20 17:xx）
> 目标：右侧栏从"通用浏览器"改为"AI 操作副作用管理器"
> 主线：AI 干了什么 → 有何副作用 → 怎么管理

### 变更追踪（原资源管理器 → 改造）
- [x] 新增内部模块 `actions/_change_tracker.py`：ChangeTracker 单例，文件类动作执行前拍快照、执行后记状态（改/增/删）+操作次数
- [x] `action.py`：新增 `_load_change_tracker()`；`execute_action` 里文件类动作执行前 before()、成功后 after()（覆盖 file_write/file_append/file_delete/replace_lines/smart_patch）
- [x] `api.py`：新增 `get_changes` / `get_change_diff` / `clear_changes` 三个桥接
- [x] `webui/demo.html`：panel-files 改为 panel-changes（徽标+文件+操作次数+点开 diff）
- [x] diff 视图：difflib.unified_diff（会话初始快照 vs 当前），超 400 行截断

### 任务进度（原技能记录 → 改造）
- [x] panel-history 改为 panel-tasks，renderHistory 重写为时间线样式（当前任务高亮、图标+类型+摘要+时间）

### 会话概览小卡（新增）
- [x] 右侧栏顶部 session-overview：改了N文件 / 起了M服务 / 执行K动作，随动作完成自动刷新

### 本地服务增强（保留+增强）
- [x] 搜索框：按服务名/id/命令过滤 + 日志关键字高亮（mark.svc-hit）

### 关键修复
- [x] `esc()` 容错：原来 `s.replace` 在数字入参时报 "s.replace is not a function"，改为 String(s) + 空值保护
- [x] diff 双换行 bug：splitlines(keepends=True) + unified_diff(lineterm) 叠加，改为 splitlines() + lineterm=""
- [x] fsReveal 兼容：资源管理器面板删除后改为直接调系统资源管理器定位
- [x] addHistory 触发变更面板防抖刷新（800ms）

### 验证
- [x] py_compile 全量 OK
- [x] node --check app.js OK；CSS 大括号平衡 0
- [x] 后端端到端：file_write/append/delete 全被追踪，diff 正确
- [x] 前端 Playwright：三面板渲染/diff 展开/服务搜索过滤+高亮/概览计数/自动刷新 全通过，无 console 报错
- 【待办·未做】变更追踪的「一键回滚」（本喵选的是 B 档：清单+diff，不含回滚）；快照目前随会话累积在 service_logs/_change_snapshots/，长会话需考虑清理策略