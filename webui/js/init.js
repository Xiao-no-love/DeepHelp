        function start_animation() {
            var g = document.getElementById('geo'),
                s = document.getElementById('splash'),
                ct = g.querySelector('.ct'),
                bt = g.querySelector('.bt'),
                rw = g.querySelectorAll('.rw'),
                ln = g.querySelectorAll('.ln');

            // 全黑起手 → 中心点点亮
            setTimeout(function () { ct.classList.add('on'); }, 100);

            // 圆环依次绽放
            [250, 420, 580, 740].forEach(function (d, i) {
                setTimeout(function () { rw[i].classList.add('on'); }, d);
            });

            // 射线依次延伸
            [320, 380, 440, 500, 560, 620, 680, 740].forEach(function (d, i) {
                setTimeout(function () { ln[i].classList.add('on'); }, d);
            });

            // LOADING 文字浮现
            setTimeout(function () { bt.classList.add('on'); }, 900);

            // 彩色绽放 + 中心光晕爆发（全亮瞬间）
            setTimeout(function () {
                g.classList.add('c');
                s.classList.add('bloom');
            }, 1300);

            // 光晕炸开的同时，图形消散 + 遮罩开始淡出，露出主界面
            setTimeout(function () {
                g.classList.add('diss');
                s.classList.add('out');
            }, 1450);

            // 彻底移除 splash 节点
            setTimeout(function () {
                if (s && s.parentNode) s.parentNode.removeChild(s);
            }, 2600);
        }

        start_animation();