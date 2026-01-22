document.addEventListener('DOMContentLoaded', async () => {
    const loadingDiv = document.getElementById('data-loading');
    const errorDiv = document.getElementById('data-error');
    const chartsArea = document.getElementById('charts-area');

    // 自动获取数据库路径，加时间戳防止缓存
    const dbFilePath = './reservoirs.db?' + new Date().getTime();

    try {
        // 1. 初始化 SQL.js
        const SQL = await initSqlJs({ 
            locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}` 
        });

        console.log("正在下载数据库文件...");
        const response = await fetch(dbFilePath);
        if (!response.ok) throw new Error("无法获取数据库文件，请确认 reservoirs.db 是否在仓库中。");
        
        const buffer = await response.arrayBuffer();
        const db = new SQL.Database(new Uint8Array(buffer));

        // 2. 查询数据
        const stmt = db.prepare("SELECT * FROM reservoir_data ORDER BY record_time ASC");
        const allData = [];
        while (stmt.step()) {
            allData.push(stmt.getAsObject());
        }
        stmt.free();

        if (allData.length === 0) {
            throw new Error("数据库中没有记录。");
        }

        // 3. 渲染图表
        renderCharts(allData);
        loadingDiv.style.display = 'none';

    } catch (error) {
        console.error("详细错误:", error);
        loadingDiv.style.display = 'none';
        errorDiv.textContent = `加载失败: ${error.message}`;
        errorDiv.style.display = 'block';
    }
});

function renderCharts(allData) {
    const chartsArea = document.getElementById('charts-area');
    chartsArea.innerHTML = ''; 

    // 按水库名称分组
    const groups = allData.reduce((acc, row) => {
        if (!acc[row.name]) acc[row.name] = [];
        acc[row.name].push(row);
        return acc;
    }, {});

    Object.keys(groups).forEach(name => {
        const data = groups[name];

        // 1. 创建卡片容器 (对应你 HTML 中的 reservoir-card)
        const card = document.createElement('div');
        card.className = 'reservoir-card';
        card.innerHTML = `
            <h2>${name} 水库运行实时监测</h2>
            <div id="chart-${name}" class="chart-container" style="height: 500px;"></div>
        `;
        chartsArea.appendChild(card);

        const myChart = echarts.init(document.getElementById(`chart-${name}`));

        // 提取数据
        const times = data.map(item => item.record_time);
        const capacities = data.map(item => item.capacity_level); // 亿m³
        const levels = data.map(item => item.water_level);       // m
        const inflows = data.map(item => item.inflow);           // m³/s
        const outflows = data.map(item => item.outflow);         // m³/s

        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' }
            },
            legend: { 
                data: ['储水量', '水位', '入库流量', '出库流量'],
                top: 0
            },
            grid: { 
                left: '10%', 
                right: '10%', 
                bottom: '15%', 
                top: '15%',
                containLabel: true 
            },
            xAxis: { 
                type: 'category', 
                boundaryGap: false, 
                data: times,
                axisLabel: {
                    formatter: (value) => value.split(' ')[0] + '\n' + (value.split(' ')[1] || ''),
                    rotate: 0
                }
            },
            yAxis: [
                {
                    type: 'value',
                    name: '储水量(亿m³)',
                    position: 'left',
                    scale: true, // 不从0开始，让波动更明显
                    axisLine: { show: true, lineStyle: { color: '#5470c6' } },
                    axisLabel: { formatter: '{value}' }
                },
                {
                    type: 'value',
                    name: '流量(m³/s)',
                    position: 'right',
                    axisLine: { show: true, lineStyle: { color: '#ee6666' } },
                    splitLine: { show: false }
                },
                {
                    type: 'value',
                    name: '水位(m)',
                    position: 'left',
                    offset: 70, // 将第三个轴向左偏移，防止重叠
                    scale: true,
                    axisLine: { show: true, lineStyle: { color: '#91cc75' } },
                    splitLine: { show: false }
                }
            ],
            series: [
                {
                    name: '储水量',
                    type: 'line',
                    yAxisIndex: 0,
                    data: capacities,
                    smooth: true,
                    areaStyle: { opacity: 0.1 },
                    itemStyle: { color: '#5470c6' }
                },
                {
                    name: '水位',
                    type: 'line',
                    yAxisIndex: 2,
                    data: levels,
                    smooth: true,
                    itemStyle: { color: '#91cc75' }
                },
                {
                    name: '入库流量',
                    type: 'line',
                    yAxisIndex: 1,
                    data: inflows,
                    smooth: true,
                    lineStyle: { width: 2, type: 'dashed' },
                    itemStyle: { color: '#fac858' }
                },
                {
                    name: '出库流量',
                    type: 'line',
                    yAxisIndex: 1,
                    data: outflows,
                    smooth: true,
                    itemStyle: { color: '#ee6666' }
                }
            ]
        };

        myChart.setOption(option);
        // 响应式
        window.addEventListener('resize', () => myChart.resize());
    });
}
