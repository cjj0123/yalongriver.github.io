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
                title: { text: name + ' 运行详情', left: 'center' },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'shadow' }
                },
                // 四个指标的图例
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
