document.addEventListener('DOMContentLoaded', async () => {
    const loadingDiv = document.getElementById('data-loading');
    const errorDiv = document.getElementById('data-error');
    const chartsArea = document.getElementById('charts-area');

    // 自动获取数据库路径
    const dbFilePath = './reservoirs.db?' + new Date().getTime(); // 加时间戳防止缓存

    try {
        const SQL = await initSqlJs({ 
            locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}` 
        });

        console.log("正在下载数据库文件...");
        const response = await fetch(dbFilePath);
        if (!response.ok) throw new Error("无法获取数据库文件，请确认 reservoirs.db 是否在仓库根目录。");
        
        const buffer = await response.arrayBuffer();
        const db = new SQL.Database(new Uint8Array(buffer));

        // --- 调试代码：检查数据库结构 ---
        const tableCheck = db.exec("SELECT name FROM sqlite_master WHERE type='table';");
        console.log("数据库中的表:", tableCheck);

        if (tableCheck.length === 0 || tableCheck[0].values.length === 0) {
            throw new Error("数据库是空的（没有任何表）。");
        }

        const rowCount = db.exec("SELECT COUNT(*) FROM reservoir_data;");
        console.log("数据总行数:", rowCount[0].values[0][0]);
        // ------------------------------

        const stmt = db.prepare("SELECT * FROM reservoir_data ORDER BY record_time ASC");
        const allData = [];
        while (stmt.step()) {
            allData.push(stmt.getAsObject());
        }
        stmt.free();

        if (allData.length === 0) {
            loadingDiv.style.display = 'none';
            errorDiv.innerHTML = "数据库已找到，但 <b>reservoir_data</b> 表中没有任何记录。<br>请检查爬虫是否成功写入了数据。";
            errorDiv.style.display = 'block';
            return;
        }

        // 数据分组逻辑 (保持不变...)
        renderCharts(allData);
        loadingDiv.style.display = 'none';

    } catch (error) {
        console.error("详细错误信息:", error);
        loadingDiv.style.display = 'none';
        errorDiv.textContent = `失败: ${error.message}`;
        errorDiv.style.display = 'block';
    }
});

function renderCharts(allData) {
    const chartsArea = document.getElementById('charts-area');
    chartsArea.innerHTML = ''; 

    const groups = allData.reduce((acc, row) => {
        if (!acc[row.name]) acc[row.name] = [];
        acc[row.name].push(row);
        return acc;
    }, {});

    Object.keys(groups).forEach(name => {
        const data = groups[name];
        const chartWrapper = document.createElement('div');
        chartWrapper.className = 'chart-container';
        chartWrapper.style.marginBottom = "50px";
        chartWrapper.innerHTML = `
            <h2 style="text-align:center;">${name} 水情监控</h2>
            <div id="chart-${name}" style="width: 100%; height: 500px;"></div>
        `;
        chartsArea.appendChild(chartWrapper);

        const myChart = echarts.init(document.getElementById(`chart-${name}`));

        // 提取数据
        const times = data.map(item => item.record_time);
        const capacities = data.map(item => item.capacity_level); // 储水量 (亿m³)
        const levels = data.map(item => item.water_level);       // 水位 (m)
        const inflows = data.map(item => item.inflow);           // 入库 (m³/s)
        const outflows = data.map(item => item.outflow);         // 出库 (m³/s)

        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' }
            },
            legend: { 
                data: ['储水量', '水位', '入库流量', '出库流量'],
                top: 25
            },
            grid: { left: '5%', right: '5%', bottom: '10%', containLabel: true },
            xAxis: { type: 'category', boundaryGap: false, data: times },
            yAxis: [
                {
                    type: 'value',
                    name: '储水量(亿m³)',
                    position: 'left',
                    scale: true, // 关键：不从0开始，防止曲线被压扁
                    axisLine: { show: true, lineStyle: { color: '#5470c6' } },
                    axisLabel: { formatter: '{value} 亿' }
                },
                {
                    type: 'value',
                    name: '流量(m³/s)',
                    position: 'right',
                    axisLine: { show: true, lineStyle: { color: '#ee6666' } },
                    axisLabel: { formatter: '{value}' },
                    splitLine: { show: false }
                },
                {
                    type: 'value',
                    name: '水位(m)',
                    position: 'left',
                    offset: 60, // 将水位轴向左偏移，避免跟储水量重叠
                    scale: true, 
                    axisLine: { show: true, lineStyle: { color: '#91cc75' } },
                    axisLabel: { formatter: '{value} m' },
                    splitLine: { show: false }
                }
            ],
            series: [
                {
                    name: '储水量',
                    type: 'line',
                    yAxisIndex: 0, // 使用第一个左轴
                    data: capacities,
                    smooth: true,
                    itemStyle: { color: '#5470c6' },
                    areaStyle: { opacity: 0.2 }
                },
                {
                    name: '水位',
                    type: 'line',
                    yAxisIndex: 2, // 使用偏移的左轴
                    data: levels,
                    smooth: true,
                    itemStyle: { color: '#91cc75' }
                },
                {
                    name: '入库流量',
                    type: 'line',
                    yAxisIndex: 1, // 使用右轴
                    data: inflows,
                    smooth: true,
                    lineStyle: { width: 2, type: 'dashed' },
                    itemStyle: { color: '#fac858' }
                },
                {
                    name: '出库流量',
                    type: 'line',
                    yAxisIndex: 1, // 使用右轴
                    data: outflows,
                    smooth: true,
                    lineStyle: { width: 2 },
                    itemStyle: { color: '#ee6666' }
                }
            ]
        };

        myChart.setOption(option);
        window.addEventListener('resize', () => myChart.resize());
    });
}
