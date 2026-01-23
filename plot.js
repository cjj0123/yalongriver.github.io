document.addEventListener('DOMContentLoaded', async () => {
    const loading = document.getElementById('data-loading');
    const errorDiv = document.getElementById('data-error');
    const chartsArea = document.getElementById('charts-area');

    try {
        const SQL = await initSqlJs(window.sqlJsConfig);
        
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

        values.forEach(row => {
            const name = row[columns.indexOf('name')];
            if (!grouped[name]) {
                grouped[name] = { time: [], water: [], inflow: [], outflow: [], capacity: [] };
            }
            grouped[name].time.push(row[columns.indexOf('record_time')]);
            grouped[name].water.push(row[columns.indexOf('water_level')]);
            grouped[name].inflow.push(row[columns.indexOf('inflow')]);
            grouped[name].outflow.push(row[columns.indexOf('outflow')]);
            grouped[name].capacity.push(row[columns.indexOf('capacity_level')]);
        });

        loading.style.display = 'none';

        // 3. 渲染图表
        Object.keys(grouped).forEach(name => {
            const card = document.createElement('div');
            card.className = 'reservoir-card';
            card.innerHTML = `<h2>${name} 水库</h2><div id="chart_${name}" class="chart-container"></div>`;
            chartsArea.appendChild(card);

            const chart = echarts.init(document.getElementById(`chart_${name}`));
            
            const option = {
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' }
                },
                legend: { data: ['水位', '蓄量', '入库流量', '出库流量'], bottom: 0 },
                grid: { top: '15%', left: '5%', right: '8%', bottom: '15%' },
                xAxis: {
                    type: 'category',
                    data: grouped[name].time,
                    axisLabel: { 
                        formatter: (val) => val.includes(' ') ? val.split(' ')[0] + '\n' + val.split(' ')[1] : val 
                    }
                },
                yAxis: [
                    {
                        type: 'value',
                        name: '水位 (m)',
                        position: 'left',
                        scale: true, // 核心：让水位坐标轴不从0开始，使其波动明显
                        axisLine: { show: true, lineStyle: { color: '#5470c6' } },
                        splitLine: { show: false }
                    },
                    {
                        type: 'value',
                        name: '蓄量 / 流量',
                        position: 'right',
                        axisLine: { show: true, lineStyle: { color: '#91cc75' } },
                        axisLabel: { formatter: '{value}' }
                    }
                ],
                series: [
                    {
                        name: '水位',
                        type: 'line',
                        data: grouped[name].water,
                        yAxisIndex: 0,
                        itemStyle: { color: '#5470c6' },
                        z: 10 // 让水位线显示在最上层
                    },
                    {
                        name: '蓄量',
                        type: 'line',
                        smooth: true,
                        data: grouped[name].capacity,
                        yAxisIndex: 1,
                        areaStyle: { opacity: 0.15 }, // 增加面积阴影，视觉上更好区分
                        itemStyle: { color: '#fac858' }
                    },
                    {
                        name: '入库流量',
                        type: 'line',
                        data: grouped[name].inflow,
                        yAxisIndex: 1,
                        lineStyle: { type: 'dashed', width: 1 },
                        itemStyle: { color: '#91cc75' }
                    },
                    {
                        name: '出库流量',
                        type: 'line',
                        data: grouped[name].outflow,
                        yAxisIndex: 1,
                        lineStyle: { type: 'dashed', width: 1 },
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
