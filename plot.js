document.addEventListener('DOMContentLoaded', async () => {
    const loadingDiv = document.getElementById('data-loading');
    const errorDiv = document.getElementById('data-error');
    const chartsArea = document.getElementById('charts-area');

    // 假设你的 GitHub Pages 仓库是 '你的用户名.github.io'
    // 并且 reservoirs.db 就在仓库根目录
    // 如果你的仓库名不是这样，请修改 baseURL
    const baseURL = window.location.origin + window.location.pathname.replace('index.html', '');
    const dbFilePath = baseURL + 'reservoirs.db';

    // 初始化 sql.js
    const SQL = await initSqlJs({ 
        locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}` 
    });

    try {
        // 1. 下载 SQLite 数据库文件
        const response = await fetch(dbFilePath);
        if (!response.ok) {
            throw new Error(`Failed to fetch database: ${response.statusText}`);
        }
        const buffer = await response.arrayBuffer();

        // 2. 将文件加载到 SQL.js
        const db = new SQL.Database(new Uint8Array(buffer));

        // 3. 查询所有数据
        const stmt = db.prepare("SELECT name, record_time, water_level, inflow, outflow, capacity_level FROM reservoir_data ORDER BY record_time ASC");
        const result = stmt.getAsObject({}); // 获取所有行
        const allData = [];

        // 将结果转换为更易处理的数组
        while (stmt.step()) {
            allData.push(stmt.getAsObject());
        }
        stmt.free();
        db.close();

        if (allData.length === 0) {
            errorDiv.textContent = "数据库中没有找到任何数据。";
            errorDiv.style.display = 'block';
            loadingDiv.style.display = 'none';
            return;
        }

        // 4. 按水库名称分组数据
        const dataByReservoir = {};
        for (const row of allData) {
            if (!dataByReservoir[row.name]) {
                dataByReservoir[row.name] = {
                    timestamps: [],
                    water_levels: [],
                    inflows: [],
                    outflows: [],
                    capacity_levels: []
                };
            }
            dataByReservoir[row.name].timestamps.push(row.record_time);
            dataByReservoir[row.name].water_levels.push(row.water_level);
            dataByReservoir[row.name].inflows.push(row.inflow);
            dataByReservoir[row.name].outflows.push(row.outflow);
            dataByReservoir[row.name].capacity_levels.push(row.capacity_level);
        }

        loadingDiv.style.display = 'none';
        
        // 5. 遍历每个水库，创建图表
        for (const reservoirName in dataByReservoir) {
            const data = dataByReservoir[reservoirName];

            // 创建卡片和图表容器
            const card = document.createElement('div');
            card.className = 'reservoir-card';
            chartsArea.appendChild(card);

            const title = document.createElement('h2');
            title.textContent = `${reservoirName} 水库运行数据`;
            card.appendChild(title);

            const chartDivId = `chart-${reservoirName.replace(/\s+/g, '-')}`;
            const chartDiv = document.createElement('div');
            chartDiv.id = chartDivId;
            chartDiv.className = 'chart-container';
            card.appendChild(chartDiv);

            // 初始化 ECharts 实例
            const myChart = echarts.init(chartDiv);

            // 配置 ECharts 选项
            const option = {
                tooltip: {
                    trigger: 'axis',
                    formatter: function (params) {
                        let res = `时间: ${params[0].name}<br/>`;
                        params.forEach(item => {
                            if (item.value !== null) { // 排除 null 值
                                res += `${item.marker}${item.seriesName}: ${item.value} ${item.seriesName === '库水位' ? '米' : item.seriesName === '入库流量' || item.seriesName === '出库流量' ? '立方米/秒' : '亿立方米'}<br/>`;
                            }
                        });
                        return res;
                    }
                },
                legend: {
                    data: ['库水位', '入库流量', '出库流量', '库容']
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: data.timestamps.map(ts => new Date(ts).toLocaleString('zh-CN', { 
                        year: 'numeric', month: '2-digit', day: '2-digit', 
                        hour: '2-digit', minute: '2-digit' 
                    }))
                },
                yAxis: [
                    {
                        type: 'value',
                        name: '水位 (米)',
                        min: Math.min(...data.water_levels.filter(v => v !== null)) * 0.95, // 动态 Y 轴范围
                        max: Math.max(...data.water_levels.filter(v => v !== null)) * 1.05,
                        position: 'left',
                        axisLabel: {
                            formatter: '{value} 米'
                        }
                    },
                    {
                        type: 'value',
                        name: '流量 (立方米/秒) / 库容 (亿立方米)',
                        position: 'right',
                        min: 0,
                        max: Math.max(
                            ...data.inflows.filter(v => v !== null),
                            ...data.outflows.filter(v => v !== null),
                            ...data.capacity_levels.filter(v => v !== null) * 10
                        ) * 1.1, // 库容可能数值小，放大一点
                        axisLabel: {
                            formatter: '{value}'
                        }
                    }
                ],
                series: [
                    {
                        name: '库水位',
                        type: 'line',
                        yAxisIndex: 0,
                        data: data.water_levels,
                        smooth: true
                    },
                    {
                        name: '入库流量',
                        type: 'line',
                        yAxisIndex: 1,
                        data: data.inflows,
                        smooth: true
                    },
                    {
                        name: '出库流量',
                        type: 'line',
                        yAxisIndex: 1,
                        data: data.outflows,
                        smooth: true
                    },
                    {
                        name: '库容',
                        type: 'line',
                        yAxisIndex: 1,
                        data: data.capacity_levels,
                        smooth: true
                    }
                ]
            };
            myChart.setOption(option);

            // 响应式调整图表大小
            window.addEventListener('resize', function () {
                myChart.resize();
            });
        }

    } catch (error) {
        console.error("数据加载或处理错误:", error);
        loadingDiv.style.display = 'none';
        errorDiv.textContent = `加载数据失败: ${error.message}`;
        errorDiv.style.display = 'block';
    }
});
