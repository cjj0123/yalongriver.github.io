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
    chartsArea.innerHTML = ''; // 清空现有内容

    // 1. 数据按水库名称分组
    const groups = allData.reduce((acc, row) => {
        if (!acc[row.name]) {
            acc[row.name] = [];
        }
        acc[row.name].push(row);
        return acc;
    }, {});

    console.log("识别到的水库列表:", Object.keys(groups));

    // 2. 遍历每个水库，创建一个图表
    Object.keys(groups).forEach(name => {
        const data = groups[name];

        // 创建图表容器外层
        const chartWrapper = document.createElement('div');
        chartWrapper.className = 'chart-container';
        chartWrapper.innerHTML = `<h3>${name}</h3><div id="chart-${name}" style="width: 100%; height: 400px;"></div>`;
        chartsArea.appendChild(chartWrapper);

        // 初始化 ECharts
        const chartDom = document.getElementById(`chart-${name}`);
        const myChart = echarts.init(chartDom);

        // 准备坐标轴数据
        const times = data.map(item => item.record_time);
        const percentages = data.map(item => item.percentage); // 蓄水率
        const levels = data.map(item => item.water_level);     // 水位

        const option = {
            tooltip: {
                trigger: 'axis',
                formatter: function (params) {
                    let res = params[0].name + '<br/>';
                    params.forEach(item => {
                        res += `${item.seriesName}: ${item.value} ${item.seriesName === '蓄水率' ? '%' : 'm'}<br/>`;
                    });
                    return res;
                }
            },
            legend: { data: ['蓄水率', '水位'] },
            grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: times
            },
            yAxis: [
                {
                    type: 'value',
                    name: '蓄水率(%)',
                    min: 0,
                    max: 100,
                    axisLabel: { formatter: '{value} %' }
                },
                {
                    type: 'value',
                    name: '水位(m)',
                    splitLine: { show: false }
                }
            ],
            series: [
                {
                    name: '蓄水率',
                    type: 'line',
                    data: percentages,
                    smooth: true,
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: 'rgba(58, 77, 233, 0.8)' },
                            { offset: 1, color: 'rgba(58, 77, 233, 0.1)' }
                        ])
                    }
                },
                {
                    name: '水位',
                    type: 'line',
                    yAxisIndex: 1,
                    data: levels,
                    smooth: true,
                    lineStyle: { color: '#ff7ed1' }
                }
            ]
        };

        myChart.setOption(option);

        // 响应式窗口大小变化
        window.addEventListener('resize', () => myChart.resize());
    });
}
