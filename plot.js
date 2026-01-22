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
    // 这里放你之前的分组和 ECharts 渲染逻辑
    console.log("准备渲染图表，数据量:", allData.length);
    // ... (此处省略重复的渲染代码，请保留你之前 plot.js 里的 render 逻辑)
}
