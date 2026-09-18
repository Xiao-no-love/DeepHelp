        // ====== 初始化 marked ======
        // breaks:false —— 单个回车不再强转 <br>（避免 AI 输出里行内换行被撑开）；段落靠空行分隔
        try { marked.setOptions({ breaks: false, gfm: true }); } catch (e) { }
        // ====== 依赖自愈：vendor 脚本若因瞬时连接问题没加载上，自动重试 ======
        // 背景：pywebview 内置 http 服务器并发拉取多个资源时偶发 ERR_CONNECTION_REFUSED，
        // 导致 marked / DOMPurify 缺失、markdown 退化成未渲染原文。这里带 cache-buster 重试，
        // 彻底失败时明确提示，而不是静默降级。
        (function ensureVendorLibs() {
            var libs = [
                { name: 'marked', test: function () { return !!window.marked; }, src: 'vendor/js/marked.min.js' },
                { name: 'DOMPurify', test: function () { return !!window.DOMPurify; }, src: 'vendor/js/purify.min.js' },
                { name: 'hljs', test: function () { return !!window.hljs; }, src: 'vendor/js/highlight.min.js' }
            ];
            var round = 0, MAX = 8;
            function missing() { return libs.filter(function (l) { return !l.test(); }); }
            (function attempt() {
                var miss = missing();
                if (!miss.length) return;
                if (round >= MAX) {
                    var msg = '渲染库加载失败(' + miss.map(function (l) { return l.name; }).join(',') + ')，请重启程序';
                    try { if (window.showToast) window.showToast(msg); } catch (e) { }
                    try { console.error('[DeepHelp] ' + msg); } catch (e) { }
                    return;
                }
                round++;
                miss.forEach(function (l) {
                    var s = document.createElement('script');
                    s.src = l.src + '?_r=' + round + '_' + Date.now();
                    s.async = false;
                    document.head.appendChild(s);
                });
                setTimeout(attempt, 400);
            })();
        })();
        // ====== 全局状态 ======
        var chatEl = document.getElementById('chat-list');
        var inputEl = document.getElementById('input');
        var sendBtn = document.getElementById('send-btn');
        var historyList = document.getElementById('side-history-list');
        var historyCount = document.getElementById('history-count');
        var historyData = [];
        var actionCounter = 0;
        var agentInitialized = false;
        var agentBusy = false;
        var modalConfirmAction = null;
        var sentChars = 0;
        var receivedChars = 0;
        var commandCount = 0;
        var randCharType = null;
        var virtualMessageDiv = null;
        function updateStats() {
            var el = document.getElementById('chat-stats');
            if (!el) return;
            el.innerHTML =
                '<span>发送 ' + sentChars + '</span><span class="stat-sep"></span>' +
                '<span>收到 ' + receivedChars + '</span><span class="stat-sep"></span>' +
                '<span>总计 ' + (sentChars + receivedChars) + '</span><span class="stat-sep"></span>' +
                '<span>命令 ' + commandCount + '</span>';
        }
        // ====== 工具函数 ======
        function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
        function scrollBottom(el) { el.scrollTop = el.scrollHeight }
        function msToStr(ms) { if (ms < 1000) return ms + 'ms'; if (ms < 60000) return (ms / 1000).toFixed(1) + 's'; return (ms / 60000).toFixed(1) + 'min' }
        function showToast(msg) {
            var t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            clearTimeout(t._timer);
            t._timer = setTimeout(function () { t.classList.remove('show') }, 1800);
        }
        // ====== 背景控制 ======
        function applyBlur(val) {
            document.documentElement.style.setProperty('--blur-card', val + 'px');
        }
        function applyFontScale(val) {
            var n = parseInt(val, 10);
            if (isNaN(n) || n <= 0) n = 100;
            document.documentElement.style.setProperty('--fs', (n / 100).toString());
        }
        function applyBackground(path) {
            var body = document.body;
            if (path && path.trim() !== '') {
                var p = path.replace(/\\/g, '/');
                if (!/^(https?:|file:|data:)/i.test(p)) {
                    p = 'file:///' + p;
                }
                body.style.backgroundImage = 'url("' + p + '")';
                body.classList.add('bg-image');
            } else {
                body.style.backgroundImage = '';
                body.classList.remove('bg-image');
            }
        }
        function removeBackground() {
            applyBackground('');
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_background('');
            }
            showToast('已移除背景');
        }
        function browseImage(fieldId) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.browse_background(fieldId);
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        // ====== 状态栏 ======
        function setStatus(obj) {
            var dot = document.getElementById('sb-dot');
            var st = document.getElementById('sb-status');
            // 兼容旧字段：state 缺失时按 connected 推断
            var state = obj.state;
            if (!state) {
                state = obj.connected === true ? 'connected'
                    : obj.connected === false ? 'disconnected' : 'connecting';
            }
            var label = { connected: '已连接', connecting: '连接中...',
                          error: '连接错误', disconnected: '未连接' }[state] || state;
            // 有进度文案（如"限速等待 3s..."）时优先显示
            st.textContent = obj.msg ? obj.msg : label;
            dot.className = 'dot ' + (state === 'connected' ? 'on'
                : state === 'connecting' ? 'connecting'
                : state === 'error' ? 'error' : 'off');
            document.getElementById('sb-port').textContent = '端口: ' + (obj.port || '--');
            var pg = document.getElementById('sb-page');
            var url = obj.page_url || '';
            pg.textContent = '页面: ' + (url ? url.replace(/^https?:\/\//, '').slice(0, 40) : '--');
            pg.title = url;
            var cwdEl = document.getElementById('sb-cwd');
            cwdEl.textContent = 'CWD: ' + (obj.cwd || '--');
            cwdEl.title = obj.cwd_full || '';
            // 驱动自动模式徽章
            setAutoMode({ on: !!obj.auto_mode, round: obj.auto_round || 0, max: obj.auto_max || 5 });
        }
        // ====== 消息 ======
        function applyFadeInChildren(el) {
            var children = Array.from(el.children);
            children.forEach(function (child, idx) {
                // 先置 0 并挂过渡
                child.style.transition = "opacity 0.35s ease";
                child.style.opacity = "0";
                // 用 setTimeout 错开呈现，绝不依赖 requestAnimationFrame：
                // WebView2 在窗口后台/最小化/被遮挡时会暂停 rAF 回调，
                // 若把 opacity:1 放在 rAF 里，内容会永远停在透明状态——
                // 表现为"DOM 里明明有内容却看不见"，切回前台才出现（时好时坏的假死）。
                setTimeout(function () {
                    // 强制重排：确保 0→1 的样式变化被浏览器观察到，过渡才会触发
                    void child.offsetHeight;
                    child.style.opacity = "1";
                }, 20 + idx * 60);
            });
        }

        // ====== 题目(quiz)：AI 提问 → 用户作答 → 回传 ======
        function parseQuiz(body) {
            var q = { type: 'single', question: '', options: [] };
            var lines = body.split('\n');
            var cur = null;
            for (var i = 0; i < lines.length; i++) {
                var t = lines[i].trim();
                if (!t) continue;
                var km = t.match(/^(type|question)\s*[:：]\s*(.*)$/);
                if (km) { q[km[1]] = km[2].trim(); cur = null; continue; }
                var om = t.match(/^([A-Za-z])\s*[\.、．\):：]\s*(.+)$/);
                if (om) { cur = { key: om[1].toUpperCase(), text: om[2].trim() }; q.options.push(cur); continue; }
                if (cur) cur.text += ' ' + t;
            }
            q.type = (q.type || 'single').toLowerCase();
            if (['single', 'multiple', 'blank'].indexOf(q.type) < 0) q.type = 'single';
            if (!q.question && !q.options.length) return null;
            return q;
        }
        function buildQuizHTML(q) {
            var label = { single: '单选', multiple: '多选', blank: '填空' }[q.type] || '单选';
            var h = '<div class="quiz-item" data-type="' + q.type + '" data-q="' + esc(q.question) + '">';
            h += '<div class="quiz-head"><span class="quiz-badge">' + label + '</span>';
            var qt = esc(q.question);
            if (q.type === 'blank') qt = qt.replace(/_{2,}/g, '<input type="text" class="quiz-blank">');
            h += '<span class="quiz-q">' + qt + '</span></div>';
            if (q.type !== 'blank') {
                h += '<div class="quiz-opts">';
                for (var i = 0; i < q.options.length; i++) {
                    var o = q.options[i];
                    h += '<div class="quiz-opt" data-key="' + o.key + '"><span class="quiz-key">'
                        + o.key + '</span><span class="quiz-opt-text">' + esc(o.text) + '</span></div>';
                }
                h += '<div class="quiz-opt-custom"><span class="quiz-key">+</span>'
                    + '<input type="text" class="quiz-custom-input" placeholder="其他（自行输入）"></div>';
                h += '</div>';
            }
            h += '</div>';
            return h;
        }
        function renderMessageHTML(text) {
            var re = /```quiz\s*\n([\s\S]*?)```/g;
            var quizzes = [];
            var replaced = text.replace(re, function (_, body) {
                var q = parseQuiz(body);
                if (!q) return _;
                quizzes.push(q);
                return '\n\n@@QUIZ_' + (quizzes.length - 1) + '@@\n\n';
            });
            var html = marked.parse(replaced);
            if (quizzes.length) {
                var block = '<div class="quiz-group" data-count="' + quizzes.length + '">';
                for (var k = 0; k < quizzes.length; k++) block += buildQuizHTML(quizzes[k]);
                block += '<div class="quiz-actions"><button class="quiz-submit" type="button" disabled>提交选择</button>'
                    + '<span class="quiz-tip">请至少作答一题</span></div></div>';
                var done = false;
                var inject = function () { if (done) return ''; done = true; return block; };
                html = html.replace(/<p>\s*@@QUIZ_(\d+)@@\s*<\/p>/g, inject);
                html = html.replace(/@@QUIZ_(\d+)@@/g, inject);
            }
            return html;
        }
        // 把消息内的每个 <table> 包进 .table-wrap，实现横向滚动（CSS 无法直接给裸 table 加滚动）
        function wrapTables(container) {
            if (!container || !container.querySelectorAll) return;
            var tables = container.querySelectorAll('table');
            for (var i = 0; i < tables.length; i++) {
                var t = tables[i];
                if (t.parentNode && t.parentNode.classList &&
                    t.parentNode.classList.contains('table-wrap')) continue;
                var wrap = document.createElement('div');
                wrap.className = 'table-wrap';
                t.parentNode.insertBefore(wrap, t);
                wrap.appendChild(t);
            }
        }
        function collectQuizAnswers(group) {
            var items = group.querySelectorAll('.quiz-item');
            var lines = [];
            var any = false;
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var type = it.getAttribute('data-type');
                var qtext = it.getAttribute('data-q') || ('第' + (i + 1) + '题');
                var ans = '';
                if (type === 'blank') {
                    var inp = it.querySelector('.quiz-blank');
                    ans = (inp ? inp.value : '').trim();
                } else {
                    var sel = [];
                    it.querySelectorAll('.quiz-opt.selected').forEach(function (o) {
                        var key = o.getAttribute('data-key');
                        var txt = o.querySelector('.quiz-opt-text').textContent.trim();
                        sel.push(key + '. ' + txt);
                    });
                    var ci = it.querySelector('.quiz-custom-input');
                    var custom = (ci ? ci.value : '').trim();
                    if (custom) sel.push(custom);
                    ans = sel.join('；');
                }
                if (ans) { any = true; } else { ans = '（未作答）'; }
                lines.push((i + 1) + '. ' + qtext + '\n   → ' + ans);
            }
            return { any: any, text: lines.join('\n') };
        }
        function updateQuizSubmit(group) {
            if (!group || group.getAttribute('data-submitted') === '1') return;
            var r = collectQuizAnswers(group);
            var btn = group.querySelector('.quiz-submit');
            var tip = group.querySelector('.quiz-tip');
            if (btn) btn.disabled = !r.any;
            if (tip) tip.style.display = r.any ? 'none' : '';
        }
        function submitQuiz(group) {
            if (!group || group.getAttribute('data-submitted') === '1') return;
            var r = collectQuizAnswers(group);
            if (!r.any) { showToast('请至少作答一题'); return; }
            group.setAttribute('data-submitted', '1');
            var btn = group.querySelector('.quiz-submit');
            if (btn) { btn.disabled = true; btn.textContent = '已提交'; }
            var tip = group.querySelector('.quiz-tip');
            if (tip) tip.textContent = '已提交，等待 AI 回复';
            doSend('【我的选择】\n' + r.text);
        }
        chatEl.addEventListener('click', function (e) {
            var group = e.target.closest ? e.target.closest('.quiz-group') : null;
            if (group && group.getAttribute('data-submitted') === '1') return;
            var cust = e.target.closest ? e.target.closest('.quiz-opt-custom') : null;
            if (cust) { var ci2 = cust.querySelector('.quiz-custom-input'); if (ci2) ci2.focus(); return; }
            var opt = e.target.closest ? e.target.closest('.quiz-opt') : null;
            if (opt) {
                var item = opt.closest('.quiz-item');
                if (item && item.getAttribute('data-type') === 'single') {
                    item.querySelectorAll('.quiz-opt').forEach(function (o) { o.classList.remove('selected'); });
                    var ci = item.querySelector('.quiz-custom-input');
                    if (ci) ci.value = '';
                    opt.classList.add('selected');
                } else {
                    opt.classList.toggle('selected');
                }
                updateQuizSubmit(group);
                return;
            }
            var sub = e.target.closest ? e.target.closest('.quiz-submit') : null;
            if (sub) submitQuiz(sub.closest('.quiz-group'));
        });
        chatEl.addEventListener('input', function (e) {
            var t = e.target;
            if (t.classList && t.classList.contains('quiz-custom-input')) {
                var item = t.closest('.quiz-item');
                if (item && item.getAttribute('data-type') === 'single' && (t.value || '').trim()) {
                    item.querySelectorAll('.quiz-opt').forEach(function (o) { o.classList.remove('selected'); });
                }
                updateQuizSubmit(t.closest('.quiz-group'));
            } else if (t.classList && t.classList.contains('quiz-blank')) {
                updateQuizSubmit(t.closest('.quiz-group'));
            }
        });
        function addMessage(role, text, queued) {
            if (role === 'assistant') {
                receivedChars += text.length;
                updateStats();
                // 交给 marked 解析原始文本，再用 DOMPurify 消毒（阻止 XSS）。
                // 不再预先 esc，避免代码块/实体被双重转义。
                var html = (window.marked && window.DOMPurify)
                    ? DOMPurify.sanitize(renderMessageHTML(text))
                    : esc(text);
                if (virtualMessageDiv != null && randCharType != null) {
                    clearInterval(randCharType);
                    virtualMessageDiv.innerHTML = html;
                    wrapTables(virtualMessageDiv);
                    // 新增：给markdown生成的子节点施加渐显
                    applyFadeInChildren(virtualMessageDiv);
                    virtualMessageDiv = null;
                    scrollBottom(chatEl);
                } else {
                    var div = document.createElement('div');
                    div.className = 'msg ' + role;
                    div.innerHTML = html;
                    wrapTables(div);
                    chatEl.appendChild(div);
                    applyFadeInChildren(div);
                    scrollBottom(chatEl);
                }
            } else if (role === 'user') {
                var div = document.createElement('div');
                div.className = 'msg ' + role;
                div.textContent = text;
                if (queued) {
                    // 排队消息：不触发打字机，加「排队中」标记，等下一轮真正发出
                    var tag = document.createElement('span');
                    tag.className = 'queued-tag';
                    tag.textContent = '排队中';
                    div.appendChild(tag);
                    chatEl.appendChild(div);
                    scrollBottom(chatEl);
                    return;
                }
                chatEl.appendChild(div);
                scrollBottom(chatEl);
                setTimeout(() => {
                    virtualMessage('assistant');
                }, 100);
            }
        }

        function virtualMessage(role) {
            clearInterval(randCharType);
            var div = document.createElement('div');
            div.className = 'msg ' + role;
            chatEl.appendChild(div);
            scrollBottom(chatEl);
            randCharType = setInterval(() => {
                const char = getRandomChar();
                const span = document.createElement("span");
                span.textContent = char;
                span.style.opacity = "0";
                span.style.transition = "opacity 0.35s ease";
                div.appendChild(span);
                // 同 applyFadeInChildren：不用 rAF，避免窗口后台时字符永远透明
                setTimeout(function () {
                    void span.offsetHeight;
                    span.style.opacity = "1";
                }, 20);
                scrollBottom(chatEl);
            }, 50);
            virtualMessageDiv = div;
        }
        function getRandomChar() {
            // 字符池，包含字母、数字、符号、中文、日文、韩文
            const charRanges = [
                [0x20, 0x7E],     // ASCII 可见：符号、数字、大小写英文
                [0x4E00, 0x9FA5], // 常用中文汉字
            ];
            // 随机选一个字符区间
            const [min, max] = charRanges[Math.floor(Math.random() * charRanges.length)];
            const codePoint = Math.floor(Math.random() * (max - min + 1)) + min;
            return String.fromCodePoint(codePoint);
        }
        // ====== 结构化动作气泡 ======
        function addAction(obj) {
            commandCount++;
            // 工具调用的命令与输出也计入字符统计（归入“收到”侧）
            if (obj.command) receivedChars += obj.command.length;
            if (obj.output) receivedChars += obj.output.length;
            if (obj.error) receivedChars += obj.error.length;
            updateStats();
            actionCounter++;
            obj.id = obj.id || ('act-' + actionCounter);
            var meta = null;
            if (obj.type) {
                meta = { icon: obj.icon || '', label: obj.label || obj.type, color: obj.color || '#8b949e' };
            }
            var card = document.createElement('div');
            card.className = 'action-card';
            card.id = 'action-' + obj.id;
            var hasBody = !!(obj.command || obj.output || obj.error);
            if (hasBody) card.className += ' collapsible';
            var head = '<div class="action-head">';
            if (hasBody) head += '<span class="ah-chevron"><i class="fa-solid fa-chevron-right"></i></span>';
            if (meta) head += '<span class="ah-icon"><i class="' + esc(meta.icon || '') + '"></i></span>';
            if (meta) head += '<span class="ah-type" style="color:' + esc(meta.color) + '">' + esc(meta.label) + '</span>';
            head += '<span class="ah-id">#' + esc(obj.id) + '</span>';
            var pathVal = obj.path || obj.file;
            if (pathVal) head += '<span class="ah-path" title="' + esc(pathVal) + '">' + esc(pathVal) + '</span>';
            if (obj.summary) head += '<span class="ah-summary">' + esc(obj.summary) + '</span>';
            head += '<span class="ah-spacer"></span>';
            if (obj.returncode !== undefined && obj.returncode >= 0) {
                var ok = obj.returncode === 0;
                head += '<span class="ah-rc ' + (ok ? 'ok' : 'fail') + '"><i class="fa-solid fa-' + (ok ? 'check' : 'xmark') + '"></i> 返回码: ' + obj.returncode + '</span>';
            } else if (obj.success !== undefined) {
                head += '<span class="ah-rc ' + (obj.success ? 'ok' : 'fail') + '"><i class="fa-solid fa-' + (obj.success ? 'check' : 'xmark') + '"></i> ' + (obj.success ? '成功' : '失败') + '</span>';
            }
            if (obj.duration_ms !== undefined) {
                head += '<span class="ah-time"><i class="fa-regular fa-clock"></i> ' + msToStr(obj.duration_ms) + '</span>';
            }
            head += '</div>';
            card.innerHTML = head;
            if (hasBody) {
                var body = '<div class="action-body">';
                if (obj.command) {
                    body += '<div class="action-cmd" id="cmd-' + obj.id + '">$ ' + esc(obj.command) + '</div>';
                }
                if (obj.output) {
                    var cls = obj.output.length > 600 ? ' action-output more' : ' action-output';
                    body += '<div class="' + cls + '" id="out-' + obj.id + '">' + esc(obj.output) + '</div>';
                }
                if (obj.error) {
                    body += '<div class="action-err">' + esc(obj.error) + '</div>';
                }
                if (obj.command || obj.output) {
                    body += '<div class="action-foot">';
                    if (obj.command) body += '<button onclick="copyCommand(\'' + obj.id + '\')"><i class="fa-solid fa-arrow-right-to-bracket"></i> 复制输入</button>';
                    if (obj.output) body += '<button onclick="copyOutput(\'' + obj.id + '\')"><i class="fa-solid fa-copy"></i> 复制输出</button>';
                    body += '</div>';
                }
                body += '</div>';
                card.innerHTML += body;
                card.querySelector('.action-head').addEventListener('click', function () {
                    card.classList.toggle('open');
                });
            }
            chatEl.appendChild(card);
            scrollBottom(chatEl);
            return obj;
        }
        function copyOutput(id) {
            var el = document.getElementById('out-' + id);
            if (!el) return;
            var text = el.textContent;
            navigator.clipboard.writeText(text).then(function () { showToast('已复制') });
        }
        function copyCommand(id) {
            var el = document.getElementById('cmd-' + id);
            if (!el) return;
            var text = el.textContent.replace(/^\$\s*/, '');
            navigator.clipboard.writeText(text).then(function () { showToast('已复制') });
        }
        // ====== 动作历史 ======
        var HISTORY_TTL = 7 * 24 * 3600 * 1000;   // 7 天
        function pruneHistory() {
            var now = Date.now();
            var kept = [];
            for (var i = 0; i < historyData.length; i++) {
                var t = Date.parse(historyData[i].timestamp || '');
                if (isNaN(t) || (now - t) < HISTORY_TTL) kept.push(historyData[i]);
            }
            historyData = kept;
        }
        function addHistory(obj) {
            historyData.unshift(obj);
            pruneHistory();
            renderHistory();
        }
        function histTime(h) {
            var t = Date.parse(h.timestamp || '');
            if (isNaN(t)) return '--';
            var d = new Date(t);
            var p = function (n) { return n < 10 ? '0' + n : '' + n; };
            return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
        }
        function renderHistory() {
            pruneHistory();
            if (historyCount) historyCount.textContent = historyData.length;
            var html = '';
            for (var i = 0; i < historyData.length; i++) {
                var h = historyData[i];
                var icon = h.icon || '';
                var label = h.label || h.type || '';
                var files = h.files || [];
                var pathVal = files[0] || h.path || h.file || '';
                var summary;
                if (h.command) summary = h.command;
                else if (pathVal || h.summary) summary = (pathVal ? pathVal + ' · ' : '') + (h.summary || '');
                else summary = h.type || '';
                var ok = h.returncode === 0 || h.success === true;
                var statusIcon = ok ? 'fa-check' : 'fa-xmark';
                var statusColor = ok ? '#34d399' : '#f87171';
                var dur = h.duration_ms !== undefined ? msToStr(h.duration_ms) : '--';
                html += '<div class="hist-item" data-hist-idx="' + i + '">';
                html += '<span class="hi-status" style="color:' + statusColor + '"><i class="fa-solid ' + statusIcon + '"></i></span>';
                html += '<span class="hi-icon"><i class="' + esc(icon) + '"></i></span>';
                html += '<span class="hi-type">' + esc(label) + '</span>';
                html += '<span class="hi-summary" title="' + esc(summary) + '">' + esc(summary) + '</span>';
                html += '<span class="hi-time">' + esc(histTime(h)) + ' · ' + esc(dur) + '</span>';
                html += '</div>';
                html += '<div class="hist-detail" id="hist-detail-' + i + '">';
                html += '<div>时间: ' + esc(h.timestamp || '--') + ' | 耗时: ' + esc(dur) + '</div>';
                if (h.id) html += '<div>ID: ' + esc(h.id) + '</div>';
                if (files.length) {
                    html += '<div>涉及文件:';
                    for (var k = 0; k < files.length; k++) {
                        html += ' <a class="hist-file-link" data-hist-file="' + esc(files[k]) + '">' + esc(files[k]) + '</a>';
                    }
                    html += '</div>';
                }
                if (h.command) html += '<div>命令:</div><pre>' + esc(h.command) + '</pre>';
                if (h.input) html += '<div>输入:</div><pre>' + esc(h.input) + '</pre>';
                if (h.error) html += '<div style="color:#f87171">错误: ' + esc(h.error) + '</div>';
                if (h.output) html += '<div>输出:</div><pre>' + esc(h.output) + '</pre>';
                else if (h.summary) html += '<div>结果: ' + esc(h.summary) + '</div>';
                html += '</div>';
            }
            if (historyList) historyList.innerHTML = html || '<div class="fs-empty"><i class="fa-solid fa-inbox"></i> 暂无记录</div>';
        }
        function toggleHistoryDetail(i) {
            var el = document.getElementById('hist-detail-' + i);
            if (el) el.classList.toggle('open');
        }
        function clearHistory() {
            historyData = [];
            renderHistory();
        }
        function clearChat() {
            chatEl.innerHTML = '';
            sentChars = 0;
            receivedChars = 0;
            commandCount = 0;
            updateStats();
            showToast('对话已清空');
        }
        function setAgentInitialized(val) {
            agentInitialized = val;
            var btn = document.getElementById('btn-init');
            if (btn) btn.style.opacity = val ? '0.4' : '1';
        }
        function initializeAgent() {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.initialize_agent();
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        function connectPage() {
            var dot = document.getElementById('sb-dot');
            var st = document.getElementById('sb-status');
            dot.className = 'dot connecting';
            st.textContent = '连接中...';
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.connect_page();
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        function confirmModal(options) {
            document.getElementById('modal-title').textContent = options.title || '';
            document.getElementById('modal-body').innerHTML = options.body || '';
            document.getElementById('modal-btn-confirm').textContent = options.confirmText || '确认';
            modalConfirmAction = options.onConfirm || null;
            showModal();
        }
        function showModal() {
            inputEl.blur();
            setTimeout(function () {
                document.getElementById('modal-overlay').classList.add('open');
            }, 0);
        }
        function hideModal() {
            document.getElementById('modal-overlay').classList.remove('open');
            modalConfirmAction = null;
        }
        function modalConfirm() {
            var action = modalConfirmAction;
            hideModal();
            if (action) action();
        }
        function showDropConfirm(paths) {
            if (!paths || !paths.length) return;
            var text = paths.join('\n');
            confirmModal({
                title: '填入文件路径？',
                body: '检测到 <strong>' + paths.length + '</strong> 个文件：<br><pre>' + esc(text) + '</pre>确认填入聊天输入框？',
                confirmText: '填入路径(Enter)',
                onConfirm: function () {
                    var existing = inputEl.value;
                    if (existing && !existing.endsWith('\n')) existing += '\n';
                    inputEl.value = existing + text;
                    inputEl.style.height = 'auto';
                    inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + 'px';
                    inputEl.focus();
                    showToast('已填入 ' + paths.length + ' 个文件路径');
                }
            });
        }
        document.addEventListener('keydown', function (e) {
            var overlay = document.getElementById('modal-overlay');
            if (!overlay.classList.contains('open')) return;
            if (e.key === 'Enter') {
                e.preventDefault();
                modalConfirm();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                hideModal();
            }
        });
        // ====== 设置 ======
        function loadSettings(cfg) {
            var c = cfg.chrome || {};
            document.getElementById('cfg-chrome-exe').value = c.exe || '';
            document.getElementById('cfg-chrome-port').value = c.port || 9222;
            document.getElementById('cfg-chrome-userdir').value = c.user_data_dir || '';
            document.getElementById('cfg-chrome-newwin').checked = !!c.new_window;
            document.getElementById('cfg-chrome-nofirst').checked = !!c.no_first_run;
            document.getElementById('cfg-chrome-headless').checked = !!c.headless;
            document.getElementById('cfg-chrome-extra').value = c.extra_args || '';
            document.getElementById('cfg-url').value = cfg.deepseek_url || '';
            // 动态限速：下限 + 退避上限（秒）
            var msi = cfg.min_send_interval;
            if (msi === undefined || msi === null) msi = 15;
            document.getElementById('cfg-min-interval').value = msi;
            var mxi = cfg.max_send_interval;
            if (mxi === undefined || mxi === null) mxi = 120;
            document.getElementById('cfg-max-interval').value = mxi;
            document.getElementById('cfg-maxrounds').value = cfg.max_action_rounds || 50;
            document.getElementById('cfg-timeout').value = cfg.action_timeout || 120;
            document.getElementById('cfg-shelltimeout').value = cfg.shell_timeout || 30;
            // 工作区
            document.getElementById('cfg-workdir').value = cfg.work_dir || '';
            // 资源管理器监测
            document.getElementById('cfg-watch-explorer').checked = cfg.watch_explorer !== false;
            document.getElementById('cfg-watch-interval').value = cfg.watch_interval || 2;
            // 外观
            var blur = cfg.blur_strength;
            if (blur === undefined || blur === null) blur = 24;
            document.getElementById('cfg-blur').value = blur;
            applyBlur(blur);
            // 文字大小
            var fs = cfg.font_scale;
            if (fs === undefined || fs === null) fs = 100;
            document.getElementById('cfg-fontscale').value = fs;
            applyFontScale(fs);
            // 背景
            var bgPath = cfg.background_image || '';
            document.getElementById('cfg-background').value = bgPath;
            applyBackground(cfg.background_data_url || bgPath);
        }

        function collectSettings() {
            return {
                chrome: {
                    exe: document.getElementById('cfg-chrome-exe').value.trim(),
                    port: parseInt(document.getElementById('cfg-chrome-port').value) || 9222,
                    user_data_dir: document.getElementById('cfg-chrome-userdir').value.trim(),
                    new_window: document.getElementById('cfg-chrome-newwin').checked,
                    no_first_run: document.getElementById('cfg-chrome-nofirst').checked,
                    headless: document.getElementById('cfg-chrome-headless').checked,
                    extra_args: document.getElementById('cfg-chrome-extra').value.trim()
                },
                deepseek_url: document.getElementById('cfg-url').value.trim(),
                min_send_interval: parseInt(document.getElementById('cfg-min-interval').value) || 0,
                max_send_interval: parseInt(document.getElementById('cfg-max-interval').value) || 120,
                max_action_rounds: parseInt(document.getElementById('cfg-maxrounds').value) || 50,
                action_timeout: parseInt(document.getElementById('cfg-timeout').value) || 120,
                shell_timeout: parseInt(document.getElementById('cfg-shelltimeout').value) || 30,
                work_dir: document.getElementById('cfg-workdir').value.trim() || null,
                watch_explorer: document.getElementById('cfg-watch-explorer').checked,
                watch_interval: parseInt(document.getElementById('cfg-watch-interval').value) || 2,
                background_image: document.getElementById('cfg-background').value.trim(),
                blur_strength: parseInt(document.getElementById('cfg-blur').value) || 24,
                font_scale: parseInt(document.getElementById('cfg-fontscale').value) || 100
            };
        }
        function toggleSettings() {
            document.getElementById('settings-card').classList.toggle('open');
        }
        function saveSettings() {
            var cfg = collectSettings();
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_settings(cfg);
            } else {
                showToast('请通过 pywebview 运行');
            }
            toggleSettings()
        }
        function resetSettings() {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.reset_settings();
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        function browseFile(fieldId) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.browse_file(fieldId);
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        function browseFolder(fieldId) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.browse_folder(fieldId);
            } else {
                showToast('请通过 pywebview 运行');
            }
        }
        // 覆盖浏览图片的行为，调用后端并自动应用背景
        // 在 api.py 中 browse_file 返回后会触发 loadSettings，所以不需要额外逻辑
        function setBusy(b) {
            agentBusy = b;
            // 不再禁用输入框/发送按钮：忙碌时仍可输入，消息会排队到下一轮
            var divider = document.getElementById('chat-divider');
            if (divider) {
                if (b) divider.classList.add('thinking');
                else divider.classList.remove('thinking');
            }
            inputEl.placeholder = b ? '助手处理中…（仍可输入，将排队）' : '输入消息...';
            if (!b) inputEl.focus();
        }
        function send() {
            var text = inputEl.value.trim();
            if (!text) return;
            if (!agentInitialized) {
                confirmModal({
                    title: '尚未注入系统提示词',
                    body: 'AI 回复<strong>可能不包含角色设定</strong>和<strong>可执行动作</strong>。<br>建议先点击对话栏中的 <strong>"初始化"</strong> 按钮。',
                    confirmText: '仍然发送(Enter)',
                    onConfirm: function () { doSend(text); }
                });
                return;
            }
            doSend(text);
        }
        function doSend(text) {
            setAgentInitialized(true);
            if (agentBusy) {
                // 忙时：显示带「排队中」标记的用户气泡，不再触发打字机
                addMessage('user', text, true);
                sentChars += text.length;
                updateStats();
                inputEl.value = '';
                inputEl.style.height = 'auto';
                if (window.pywebview && window.pywebview.api) {
                    window.pywebview.api.send_message(text);
                }
                return;
            }
            addMessage('user', text);
            sentChars += text.length;
            updateStats();
            inputEl.value = '';
            inputEl.style.height = 'auto';
            setBusy(true);
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.send_message(text);
            } else {
                showToast('请通过 pywebview 运行');
                setBusy(false);
            }
        }
        inputEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });
        // 自动调整文本域高度
        inputEl.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 80) + 'px';
        });
        // ====== 启动 ======
        window.addEventListener('pywebviewready', function () {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.startup().then(function () {
                    if (window.fsLoad) window.fsLoad(null);
                });
            }
        });
        // 如果已经在 pywebview 环境，直接启动
        if (window.pywebview && window.pywebview.api && window.pywebview.api.startup) {
            window.pywebview.api.startup().then(function () {
                if (window.fsLoad) window.fsLoad(null);
            });
        }
        // ====== 自动模式 & 消息排队 UI ======
        // 状态：由后端 setStatus 推送 auto_mode/auto_round/auto_max 驱动
        function setAutoMode(info) {
            var badge = document.getElementById('auto-badge');
            if (!badge) return;
            info = info || {};
            if (info.on) {
                badge.classList.add('on');
                badge.querySelector('.auto-round').textContent =
                    (info.round || 0) + '/' + (info.max || 5);
            } else {
                badge.classList.remove('on');
                badge.querySelector('.auto-round').textContent = '';
            }
        }
        function toggleAutoMode() {
            // 用当前徽章状态取反（前端只发意图，后端为准）
            var badge = document.getElementById('auto-badge');
            var on = badge && badge.classList.contains('on');
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_auto_mode_ui(!on);
            }
        }
        function pauseAutoMode() {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.pause_auto_mode();
            }
        }
        function resetAutoRound() {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.reset_auto_round();
            }
        }
        // 忙时排队的消息：右侧标「排队中」，发送前 clearQueuedBadge 清掉
        function markQueued(text) {
            // 气泡由 doSend 已显示并带「排队中」标记，这里只提示，避免重复
            showToast('已排队，将在下一轮发送');
        }
        function clearQueuedBadge() {
            var els = document.querySelectorAll('.msg.user .queued-tag');
            for (var i = 0; i < els.length; i++) els[i].remove();
        }

        // 暴露全局函数给 pywebview 调用
        window.applyBackground = applyBackground;
        window.applyFontScale = applyFontScale;
        window.setStatus = setStatus;
        window.addMessage = addMessage;
        window.addAction = addAction;
        window.addHistory = addHistory;
        window.loadSettings = loadSettings;
        window.setBusy = setBusy;
        window.showToast = showToast;
        window.clearChat = clearChat;
        window.setAgentInitialized = setAgentInitialized;
        window.initializeAgent = initializeAgent;
        window.connectPage = connectPage;
        window.showModal = showModal;
        window.hideModal = hideModal;
        window.showDropConfirm = showDropConfirm;
        window.clearHistory = clearHistory;
        window.toggleSettings = toggleSettings;
        window.saveSettings = saveSettings;
        window.resetSettings = resetSettings;
        window.browseFile = browseFile;
        window.browseFolder = browseFolder;
        window.browseImage = browseImage;
        window.removeBackground = removeBackground;
        window.copyOutput = copyOutput;
        window.toggleHistoryDetail = toggleHistoryDetail;
        window.setAutoMode = setAutoMode;
        window.toggleAutoMode = toggleAutoMode;
        window.pauseAutoMode = pauseAutoMode;
        window.resetAutoRound = resetAutoRound;
        window.markQueued = markQueued;
        window.clearQueuedBadge = clearQueuedBadge;

        // ====== 资源管理器 + 技能记录（侧边栏）======
        var fsCurrentPath = null;

        function fsFileIcon(name) {
            var ext = (name.split('.').pop() || '').toLowerCase();
            if (['js', 'ts', 'py', 'java', 'c', 'cpp', 'cs', 'go', 'rs', 'rb', 'php', 'html', 'css', 'json', 'xml', 'yml', 'yaml', 'sh'].indexOf(ext) >= 0) return 'fa-file-code';
            if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp'].indexOf(ext) >= 0) return 'fa-file-image';
            if (['md', 'txt', 'log', 'ini', 'cfg', 'conf'].indexOf(ext) >= 0) return 'fa-file-lines';
            return 'fa-file';
        }
        function fsFmtSize(n) {
            if (n < 1024) return n + 'B';
            if (n < 1048576) return (n / 1024).toFixed(1) + 'K';
            return (n / 1048576).toFixed(1) + 'M';
        }
        function fsLoad(path) {
            if (!window.pywebview || !window.pywebview.api) return;
            window.pywebview.api.list_dir(path).then(function (res) {
                if (!res || !res.ok) { showToast('打开失败: ' + ((res && res.error) || '')); return; }
                fsCurrentPath = res.path;
                var pEl = document.getElementById('fs-path');
                if (pEl) { pEl.textContent = res.path; pEl.title = res.path; }
                var listEl = document.getElementById('fs-list');
                if (!listEl) return;
                var html = '';
                if (res.parent) {
                    html += '<div class="fs-item" data-fs-dir="' + esc(res.parent.replace(/\\/g, '/')) + '">'
                        + '<span class="fs-item-icon dir"><i class="fa-solid fa-arrow-up"></i></span>'
                        + '<span class="fs-item-name">..</span></div>';
                }
                for (var i = 0; i < res.entries.length; i++) {
                    var e = res.entries[i];
                    var full = (res.path + '\\' + e.name).replace(/\\/g, '/');
                    var icon = e.dir ? 'fa-folder' : fsFileIcon(e.name);
                    var cls = e.dir ? 'dir' : 'file';
                    html += '<div class="fs-item" data-fs-' + (e.dir ? 'dir' : 'file') + '="' + esc(full) + '">'
                        + '<span class="fs-item-icon ' + cls + '"><i class="fa-solid ' + icon + '"></i></span>'
                        + '<span class="fs-item-name">' + esc(e.name) + '</span>'
                        + (e.dir ? '' : '<span class="fs-item-size">' + fsFmtSize(e.size) + '</span>')
                        + '</div>';
                }
                listEl.innerHTML = html || '<div class="fs-empty">空目录</div>';
            });
        }
        function fsRefresh() { fsLoad(fsCurrentPath); }
        function fsOpenHere() {
            if (window.pywebview && window.pywebview.api) window.pywebview.api.open_in_explorer(fsCurrentPath);
        }
        // 在内部资源管理器中定位文件：打开所在目录并高亮
        function fsReveal(filePath) {
            if (!filePath) return;
            var norm = filePath.replace(/\\/g, '/');
            var dir = norm.substring(0, norm.lastIndexOf('/'));
            var name = norm.substring(norm.lastIndexOf('/') + 1);
            if (!dir) { dir = norm; name = ''; }
            if (!window.pywebview || !window.pywebview.api) return;
            window.pywebview.api.list_dir(dir).then(function (res) {
                if (!res || !res.ok) { showToast('定位失败: ' + ((res && res.error) || '')); return; }
                fsCurrentPath = res.path;
                var pEl = document.getElementById('fs-path');
                if (pEl) { pEl.textContent = res.path; pEl.title = res.path; }
                var listEl = document.getElementById('fs-list');
                if (!listEl) return;
                var html = '';
                if (res.parent) {
                    html += '<div class="fs-item" data-fs-dir="' + esc(res.parent.replace(/\\/g, '/')) + '">'
                        + '<span class="fs-item-icon dir"><i class="fa-solid fa-arrow-up"></i></span>'
                        + '<span class="fs-item-name">..</span></div>';
                }
                for (var i = 0; i < res.entries.length; i++) {
                    var e = res.entries[i];
                    var full = (res.path + '\\' + e.name).replace(/\\/g, '/');
                    var icon = e.dir ? 'fa-folder' : fsFileIcon(e.name);
                    var cls = e.dir ? 'dir' : 'file';
                    var hit = (name && e.name === name);
                    html += '<div class="fs-item' + (hit ? ' reveal-hit' : '') + '" data-fs-' + (e.dir ? 'dir' : 'file') + '="' + esc(full) + '">'
                        + '<span class="fs-item-icon ' + cls + '"><i class="fa-solid ' + icon + '"></i></span>'
                        + '<span class="fs-item-name">' + esc(e.name) + '</span>'
                        + (e.dir ? '' : '<span class="fs-item-size">' + fsFmtSize(e.size) + '</span>')
                        + '</div>';
                }
                listEl.innerHTML = html || '<div class="fs-empty">空目录</div>';
                // 展开资源管理器面板并滚动到高亮项
                var pf = document.getElementById('panel-files');
                if (pf) pf.classList.remove('collapsed');
                var hitEl = listEl.querySelector('.reveal-hit');
                if (hitEl && hitEl.scrollIntoView) hitEl.scrollIntoView({ block: 'center' });
            });
        }
        // ====== 工作区切换提示 ======
        var wdPending = null;
        function showWorkdirSuggestion(path) {
            var bar = document.getElementById('workdir-bar');
            var pEl = document.getElementById('wd-path');
            if (!bar || !pEl) return;
            wdPending = path;
            pEl.textContent = path;
            pEl.title = path;
            bar.classList.add('show');
        }
        function hideWorkdirBar() {
            var bar = document.getElementById('workdir-bar');
            if (bar) bar.classList.remove('show');
        }
        function workdirAccept() {
            if (wdPending && window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_work_dir(wdPending).then(function (res) {
                    if (res && res.ok) {
                        showToast('工作区已切换');
                        fsLoad(res.path);
                        setStatus({ cwd: res.path.split(/[\\/]/).pop(), cwd_full: res.path });
                    } else {
                        showToast('切换失败: ' + ((res && res.error) || ''));
                    }
                });
            }
            hideWorkdirBar();
            wdPending = null;
        }
        function workdirReject() {
            if (wdPending && window.pywebview && window.pywebview.api) {
                window.pywebview.api.reject_workdir(wdPending);
            }
            hideWorkdirBar();
            wdPending = null;
        }
        function fsOpenFile(path) {
            if (!window.pywebview || !window.pywebview.api) return;
            window.pywebview.api.read_file(path).then(function (res) {
                if (!res || !res.ok) { showToast('无法预览: ' + ((res && res.error) || '')); return; }
                var nameEl = document.getElementById('fv-name');
                var codeEl = document.getElementById('fv-code');
                var viewer = document.getElementById('file-viewer');
                if (!nameEl || !codeEl || !viewer) return;
                nameEl.textContent = path;
                nameEl.title = path;
                codeEl.className = '';
                codeEl.textContent = res.content;
                if (window.hljs) {
                    var cls = (res.ext && hljs.getLanguage(res.ext)) ? res.ext : 'plaintext';
                    codeEl.className = 'language-' + cls;
                    try { hljs.highlightElement(codeEl); } catch (err) { }
                }
                viewer.setAttribute('data-path', path);
                viewer.classList.add('open');
            });
        }
        function fvClose() {
            var v = document.getElementById('file-viewer');
            if (v) v.classList.remove('open');
        }
        function fvOpenExplorer() {
            var v = document.getElementById('file-viewer');
            var p = v ? v.getAttribute('data-path') : null;
            if (p && window.pywebview && window.pywebview.api) window.pywebview.api.open_in_explorer(p);
        }
        function panelToggle(el) {
            var p = el.getAttribute('data-panel');
            var me = document.getElementById('panel-' + p);
            if (!me) return;
            var rc = document.getElementById('right-col');
            var isRow = rc && rc.classList.contains('row-layout');
            if (!me.classList.contains('collapsed')) {
                // 并排模式下允许两个都折叠；堆叠模式下至少留一个展开
                if (!isRow) {
                    var anyOpen = document.querySelector('#right-col .side-panel:not(.collapsed)');
                    if (anyOpen === me) { me.classList.add('collapsed'); return; }
                }
                me.classList.add('collapsed');
            } else {
                me.classList.remove('collapsed');
                // 仅堆叠模式：展开一个时折叠另一个
                if (!isRow) {
                    var other = document.getElementById('panel-' + (p === 'files' ? 'history' : 'files'));
                    if (other) other.classList.add('collapsed');
                }
            }
        }
        function applyRightLayout() {
            var rc = document.getElementById('right-col');
            if (!rc) return;
            var wide = rc.getBoundingClientRect().width > 700;
            var wasRow = rc.classList.contains('row-layout');
            rc.classList.toggle('row-layout', wide);
            // 进入并排：两个面板都展开
            if (wide && !wasRow) {
                var pf = document.getElementById('panel-files');
                var ph = document.getElementById('panel-history');
                if (pf) pf.classList.remove('collapsed');
                if (ph) ph.classList.remove('collapsed');
            }
        }
        window.fsLoad = fsLoad;
        window.fsRefresh = fsRefresh;
        window.fsOpenHere = fsOpenHere;
        window.fsOpenFile = fsOpenFile;
        window.fsReveal = fsReveal;
        window.fvClose = fvClose;
        window.fvOpenExplorer = fvOpenExplorer;
        window.panelToggle = panelToggle;
        window.applyRightLayout = applyRightLayout;
        window.showWorkdirSuggestion = showWorkdirSuggestion;
// ====== 事件绑定（替代内联事件，统一在 JS 中管理） ======
(function () {
    // 动作分发表
    var actions = {
        'toggle-settings': function () { toggleSettings(); },
        'win-minimize': function () { window.pywebview && window.pywebview.api && window.pywebview.api.minimize_window(); },
        'win-maximize': function () { window.pywebview && window.pywebview.api && window.pywebview.api.toggle_maximize(); },
        'toggle-auto-mode': function () { toggleAutoMode(); },
        'pause-auto-mode': function () { pauseAutoMode(); },
        'reset-auto-round': function () { resetAutoRound(); },
        'win-close': function () { window.pywebview && window.pywebview.api && window.pywebview.api.close_window(); },
        'initialize-agent': function () { initializeAgent(); },
        'connect-page': function () { connectPage(); },
        'clear-chat': function () { clearChat(); },
        'clear-history': function () { clearHistory(); },
        'browse-file': function (el) { browseFile(el.getAttribute('data-target')); },
        'browse-folder': function (el) { browseFolder(el.getAttribute('data-target')); },
        'browse-image': function (el) { browseImage(el.getAttribute('data-target')); },
        'remove-background': function () { removeBackground(); },
        'reset-settings': function () { resetSettings(); },
        'save-settings': function () { saveSettings(); },
        'send': function () { send(); },
        'hide-modal': function () { hideModal(); },
        'modal-confirm': function () { modalConfirm(); },
        'panel-toggle': function (el) { panelToggle(el); },
        'fs-refresh': function () { fsRefresh(); },
        'fs-open-here': function () { fsOpenHere(); },
        'fv-close': function () { fvClose(); },
        'fv-open': function () { fvOpenExplorer(); },
        'workdir-accept': function () { workdirAccept(); },
        'workdir-reject': function () { workdirReject(); },
        'open-workdir': function () {
            var p = document.getElementById('cfg-workdir').value.trim();
            if (p && window.pywebview && window.pywebview.api) {
                window.pywebview.api.open_in_explorer(p);
            } else {
                showToast('请先填写工作目录');
            }
        }
    };

    // 统一委托：点击
    document.addEventListener('click', function (e) {
        var histFile = e.target.closest('[data-hist-file]');
        if (histFile) {
            fsReveal(histFile.getAttribute('data-hist-file'));
            return;
        }
        var histItem = e.target.closest('[data-hist-idx]');
        if (histItem) { toggleHistoryDetail(parseInt(histItem.getAttribute('data-hist-idx'), 10)); return; }
        var fsDir = e.target.closest('[data-fs-dir]');
        if (fsDir) { fsLoad(fsDir.getAttribute('data-fs-dir')); return; }
        var fsFile = e.target.closest('[data-fs-file]');
        if (fsFile) { fsOpenFile(fsFile.getAttribute('data-fs-file')); return; }
        var el = e.target.closest('[data-action]');
        if (!el) return;
        var fn = actions[el.getAttribute('data-action')];
        if (fn) fn(el);
    });

    // 背景图片输入：变更时应用并同步后端
    var bgInput = document.getElementById('cfg-background');
    if (bgInput) {
        bgInput.addEventListener('change', function () {
            applyBackground(this.value);
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_background(this.value);
            }
        });
    }

    // 模糊度输入：实时应用
    // 模糊度输入：实时应用
    var blurInput = document.getElementById('cfg-blur');
    if (blurInput) {
        blurInput.addEventListener('input', function () {
            applyBlur(this.value);
        });
    }

    // 文字大小输入：实时应用
    var fsInput = document.getElementById('cfg-fontscale');
    if (fsInput) {
        fsInput.addEventListener('input', function () {
            applyFontScale(this.value);
        });
    }
})();
// ====== 拖拽视觉反馈 + 阻止默认打开文件 ======
// 只做 preventDefault 与高亮，不阻止冒泡——让 pywebview 的 drop 桥接仍能收到路径。
(function () {
    var hotEl = null;

    function getDropZone() {
        return document.getElementById('app') || document.body;
    }

    ['dragenter', 'dragover'].forEach(function (ev) {
        document.addEventListener(ev, function (e) {
            e.preventDefault();
            var z = getDropZone();
            if (z && !z.classList.contains('drop-hot')) z.classList.add('drop-hot');
        });
    });

    document.addEventListener('dragleave', function (e) {
        // 只在真正离开窗口时取消高亮
        if (e.target === document.documentElement || e.relatedTarget === null) {
            var z = getDropZone();
            if (z) z.classList.remove('drop-hot');
        }
    });

    document.addEventListener('drop', function (e) {
        e.preventDefault();
        var z = getDropZone();
        if (z) z.classList.remove('drop-hot');
        // 不 stopPropagation，交给 pywebview 的 drop 桥接取路径
    });
})();
/* ====== 大屏左右分栏：模式切换 + 分隔条拖动 ====== */
(function () {
    var MIN_RIGHT = 400;   // 右侧最小可用宽度
    var MIN_LEFT = 320;    // 左侧最小宽度
    var PAD = 12;          // body 左右内边距
    var KEY = 'deephelp.rightW';

    var rightCol = document.getElementById('right-col');
    var splitter = document.getElementById('splitter');
    if (!splitter || !rightCol) return;

    var userSet = false;   // 用户是否手动拖过

    function isBig() {
        return window.innerWidth > 1200 || window.innerHeight > 800;
    }
    function autoWidth() {
        var avail = window.innerWidth - PAD * 2;
        var w = Math.round(window.innerWidth * 0.42);
        var max = avail - MIN_LEFT - splitter.offsetWidth;
        if (w < MIN_RIGHT) w = MIN_RIGHT;
        if (w > max) w = max;
        return w;
    }
    function applyMode() {
        document.body.classList.toggle('big-mode', isBig());
        if (!userSet) document.documentElement.style.setProperty('--right-w', autoWidth() + 'px');
        if (window.applyRightLayout) window.applyRightLayout();
    }
    applyMode();
    window.addEventListener('resize', applyMode);

    var saved = parseInt(localStorage.getItem(KEY) || '', 10);
    if (!isNaN(saved)) {
        userSet = true;
        document.documentElement.style.setProperty('--right-w', saved + 'px');
    }

    var dragging = false;
    splitter.addEventListener('mousedown', function (e) {
        dragging = true;
        e.preventDefault();
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
    });
    splitter.addEventListener('dblclick', function () {
        userSet = false;
        localStorage.removeItem(KEY);
        document.documentElement.style.setProperty('--right-w', autoWidth() + 'px');
        if (window.applyRightLayout) window.applyRightLayout();
    });
    window.addEventListener('mousemove', function (e) {
        if (!dragging) return;
        var right = (window.innerWidth - PAD) - e.clientX;
        var max = window.innerWidth - PAD * 2 - MIN_LEFT - splitter.offsetWidth;
        if (right < MIN_RIGHT) right = MIN_RIGHT;
        if (right > max) right = max;
        document.documentElement.style.setProperty('--right-w', right + 'px');
        if (window.applyRightLayout) window.applyRightLayout();
    });
    window.addEventListener('mouseup', function () {
        if (!dragging) return;
        dragging = false;
        userSet = true;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        localStorage.setItem(KEY, Math.round(rightCol.getBoundingClientRect().width));
        if (window.applyRightLayout) window.applyRightLayout();
    });
})();
