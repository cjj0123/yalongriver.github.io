const SQL_JS_BASES = [
    'https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/',
    'https://unpkg.com/sql.js@1.8.0/dist/',
    'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/'
];

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

        values.forEach(row => {
            const name = valueOf(row, 'name');
            if (!grouped[name]) {
                grouped[name] = {
                    time: [],
                    water: [],
                    inflow: [],
                    outflow: [],
                    capacity: [],
                    energy: [],
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
            grouped[name].energy.push(valueOf(row, 'energy_level'));
            grouped[name].latestSource = valueOf(row, 'source') || '四川政务公开';
            grouped[name].latestSourceUrl = valueOf(row, 'source_url') || '';
            grouped[name].latestNote = valueOf(row, 'note') || '';
        });

        loading.style.display = 'none';

        // 3. 渲染图表
        Object.keys(grouped).forEach(name => {
            const chartId = safeId(name);
            const hasEnergy = grouped[name].energy.some(value => value !== null && value !== undefined);
            const sourceText = grouped[name].latestSourceUrl
                ? `<a href="${grouped[name].latestSourceUrl}" target="_blank" rel="noopener">${grouped[name].latestSource}</a>`
                : grouped[name].latestSource;
            const noteText = grouped[name].latestNote ? `；${grouped[name].latestNote}` : '';
            const card = document.createElement('div');
            card.className = 'reservoir-card';
            card.innerHTML = `
                <h2>${name} 水库</h2>
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
                legend: { data: hasEnergy ? ['水位', '蓄量', '蓄能', '入库', '出库'] : ['水位', '蓄量', '入库', '出库'], bottom: 0 },
                
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
                    {
                        name: '蓄能 (亿千瓦时)',
                        type: 'value',
                        gridIndex: 0,
                        position: 'right',
                        offset: hasEnergy ? 55 : 0,
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
                        name: '蓄能',
                        type: 'line',
                        xAxisIndex: 0,
                        yAxisIndex: 2,
                        data: grouped[name].energy,
                        smooth: true,
                        connectNulls: false,
                        itemStyle: { color: '#9a60b4' }
                    },
                    {
                        name: '入库',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 3,
                        data: grouped[name].inflow,
                        symbol: 'none',
                        itemStyle: { color: '#91cc75' },
                        areaStyle: { opacity: 0.1 }
                    },
                    {
                        name: '出库',
                        type: 'line',
                        xAxisIndex: 1,
                        yAxisIndex: 3,
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
