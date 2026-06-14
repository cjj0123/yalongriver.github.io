const SQL_JS_BASES = [
    'https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/',
    'https://unpkg.com/sql.js@1.8.0/dist/',
    'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/'
];
const DISPLAY_ORDER = ['两河口', '杨房沟', '锦屏一级', '官地', '二滩', '桐子林'];

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`无法加载脚本：${src}`));
        document.head.appendChild(script);
    });
}

async function loadSqlJs() {
    if (typeof initSqlJs === 'function') {
        return initSqlJs(window.sqlJsConfig);
    }

    const errors = [];
    for (const baseUrl of SQL_JS_BASES) {
        try {
            await loadScript(`${baseUrl}sql-wasm.min.js`);
            if (typeof initSqlJs !== 'function') {
                throw new Error('sql-wasm.min.js 已加载但 initSqlJs 未注册');
            }
            return await initSqlJs({
                locateFile: file => `${baseUrl}${file}`
            });
        } catch (err) {
            errors.push(err.message);
        }
    }

    throw new Error(`sql.js 加载失败，请检查网络或 CDN 访问：${errors.join('；')}`);
}

document.addEventListener('DOMContentLoaded', async () => {
    const loading = document.getElementById('data-loading');
    const errorDiv = document.getElementById('data-error');
    const chartsArea = document.getElementById('charts-area');
    const summaryDiv = document.getElementById('data-summary');
    const latestGrid = document.getElementById('latest-grid');

    try {
        const SQL = await loadSqlJs();
        
        // 1. 获取数据库文件（增加随机参数防止缓存）
        const response = await fetch('./reservoirs.db?t=' + new Date().getTime());
        if (!response.ok) throw new Error("无法加载数据库文件，请检查文件是否存在。");
        
        const buffer = await response.arrayBuffer();
        const db = new SQL.Database(new Uint8Array(buffer));

        // 2. 提取数据
        const res = db.exec("SELECT * FROM reservoir_data ORDER BY record_time ASC");
        if (res.length === 0) throw new Error("数据库中暂无数据。");

        const columns = res[0].columns;
        const values = res[0].values;
        const grouped = {};
        const col = (name) => columns.indexOf(name);
        const valueOf = (row, name) => {
            const index = col(name);
            return index >= 0 ? row[index] : null;
        };
        const safeId = (name) => `chart_${encodeURIComponent(name).replace(/%/g, '')}`;
        const escapeHtml = (value) => String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        const formatNumber = (value, digits = 2) => {
            if (value === null || value === undefined || value === '') return '-';
            const number = Number(value);
            if (!Number.isFinite(number)) return '-';
            return Number.isInteger(number) ? String(number) : number.toFixed(digits).replace(/\.?0+$/, '');
        };

        values.forEach(row => {
            const name = valueOf(row, 'name');
            if (!grouped[name]) {
                grouped[name] = {
                    time: [],
                    water: [],
                    inflow: [],
                    outflow: [],
                    capacity: [],
                    latestSource: '',
                    latestSourceUrl: '',
                    latestNote: ''
                };
            }
            grouped[name].time.push(valueOf(row, 'record_time'));
            grouped[name].water.push(valueOf(row, 'water_level'));
            grouped[name].inflow.push(valueOf(row, 'inflow'));
            grouped[name].outflow.push(valueOf(row, 'outflow'));
            grouped[name].capacity.push(valueOf(row, 'capacity_level'));
            grouped[name].latestSource = valueOf(row, 'source') || '四川政务公开';
            grouped[name].latestSourceUrl = valueOf(row, 'source_url') || '';
            grouped[name].latestNote = valueOf(row, 'note') || '';
        });

        loading.style.display = 'none';

        const reservoirNames = Object.keys(grouped).sort((a, b) => {
            const indexA = DISPLAY_ORDER.indexOf(a);
            const indexB = DISPLAY_ORDER.indexOf(b);
            if (indexA === -1 && indexB === -1) return a.localeCompare(b, 'zh-CN');
            if (indexA === -1) return 1;
            if (indexB === -1) return -1;
            return indexA - indexB;
        });
        const sourceCounts = {};
        values.forEach(row => {
            const source = valueOf(row, 'source') || '四川政务公开';
            sourceCounts[source] = (sourceCounts[source] || 0) + 1;
        });
        const xueqiuNames = reservoirNames.filter(name =>
            grouped[name].latestSource === '雪球@纬班长' ||
            values.some(row => valueOf(row, 'name') === name && valueOf(row, 'source') === '雪球@纬班长')
        );
        summaryDiv.innerHTML = [
            `当前展示 ${reservoirNames.length} 座水库/水文站`,
            `数据来源：${Object.keys(sourceCounts).join('、')}`,
            xueqiuNames.length ? `雪球补充：${xueqiuNames.join('、')}` : ''
        ].filter(Boolean).map(text => `<span class="summary-pill">${text}</span>`).join('');

        latestGrid.innerHTML = reservoirNames.map(name => {
            const item = grouped[name];
            const latestIndex = item.time.length - 1;
            const sourceText = item.latestSourceUrl
                ? `<a href="${escapeHtml(item.latestSourceUrl)}" target="_blank" rel="noopener">${escapeHtml(item.latestSource)}</a>`
                : escapeHtml(item.latestSource);
            return `
                <div class="latest-card">
                    <h3>${escapeHtml(name)}</h3>
                    <div class="latest-time">${escapeHtml(item.time[latestIndex])}</div>
                    <div class="metric-row"><span>水位</span><span>${formatNumber(item.water[latestIndex])} m</span></div>
                    <div class="metric-row"><span>入库</span><span>${formatNumber(item.inflow[latestIndex], 0)} m³/s</span></div>
                    <div class="metric-row"><span>出库</span><span>${formatNumber(item.outflow[latestIndex], 0)} m³/s</span></div>
                    <div class="metric-row"><span>蓄量</span><span>${formatNumber(item.capacity[latestIndex])} 亿m³</span></div>
                    <div class="latest-source">来源：${sourceText}</div>
                </div>
            `;
        }).join('');

        // 3. 渲染图表
        reservoirNames.forEach(name => {
            const chartId = safeId(name);
            const sourceText = grouped[name].latestSourceUrl
                ? `<a href="${escapeHtml(grouped[name].latestSourceUrl)}" target="_blank" rel="noopener">${escapeHtml(grouped[name].latestSource)}</a>`
                : escapeHtml(grouped[name].latestSource);
            const noteText = grouped[name].latestNote ? `；${escapeHtml(grouped[name].latestNote)}` : '';
            const card = document.createElement('div');
            card.className = 'reservoir-card';
            card.innerHTML = `
                <h2>${escapeHtml(name)} 运行数据</h2>
                <div class="meta-text">最新来源：${sourceText}${noteText}</div>
                <div id="${chartId}" class="chart-container"></div>
            `;
            chartsArea.appendChild(card);

            const chart = echarts.init(document.getElementById(chartId));
            
            const option = {
                title: { text: name + ' 运行详情', left: 'center' },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'shadow' }
                },
                legend: { data: ['水位', '蓄量', '入库', '出库'], bottom: 0 },
                
                // 核心：定义两个绘图区域
                grid: [
                    { left: '8%', right: '8%', top: '10%', height: '45%' }, // 上图：水位蓄量
                    { left: '8%', right: '8%', top: '65%', height: '25%' }  // 下图：流量
                ],
                
                xAxis: [
                    { 
                        type: 'category', 
                        data: grouped[name].time, 
                        gridIndex: 0, 
                        axisLabel: { show: false }, // 上图隐藏 X 轴文字
                        axisTick: { show: false }
                    },
                    { 
                        type: 'category', 
                        data: grouped[name].time, 
                        gridIndex: 1, 
                        axisLabel: { formatter: (val) => val.split(' ')[0] } // 下图显示日期
                    }
                ],
                
                yAxis: [
                    // 上图的 Y 轴
                    { 
                        name: '水位 (m)', 
                        type: 'value', 
                        gridIndex: 0, 
                        scale: true, 
                        splitLine: { show: true, lineStyle: { type: 'dashed' } } 
                    },
                    { 
                        name: '蓄量 (亿m³)', 
                        type: 'value', 
                        gridIndex: 0, 
                        position: 'right', 
                        scale: true,
                        splitLine: { show: false } 
                    },
                    // 下图的 Y 轴
                    { 
                        name: '流量 (m³/s)', 
                        type: 'value', 
                        gridIndex: 1, 
                        splitArea: { show: true } 
                    }
                ],
                
                series: [
                    {
                        name: '水位',
                        type: 'line',
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        data: grouped[name].water,
                        itemStyle: { color: '#0056b3' },
                        lineStyle: { width: 3 },
                        z: 5
                    },
                    {
                        name: '蓄量',
                        type: 'line',
                        xAxisIndex: 0,
                        yAxisIndex: 1,
                        data: grouped[name].capacity,
                        smooth: true,
                        areaStyle: { color: 'rgba(250, 200, 88, 0.2)' },
                        itemStyle: { color: '#fac858' }
                    },
                    {
                        name: '入库',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 2,
                        data: grouped[name].inflow,
                        symbol: 'none',
                        itemStyle: { color: '#91cc75' },
                        areaStyle: { opacity: 0.1 }
                    },
                    {
                        name: '出库',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 2,
                        data: grouped[name].outflow,
                        symbol: 'none',
                        itemStyle: { color: '#ee6666' }
                    }
                ]
            };
            chart.setOption(option);
        });

        // 显示最后更新时间
        const lastTime = values[values.length - 1][columns.indexOf('record_time')];
        document.getElementById('last-sync').innerText = `最后数据同步时间：${lastTime}`;

    } catch (err) {
        loading.style.display = 'none';
        errorDiv.style.display = 'block';
        errorDiv.innerText = `❌ 加载失败: ${err.message}`;
        console.error(err);
    }
});
