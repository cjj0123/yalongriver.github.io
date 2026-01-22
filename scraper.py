import sys

import datetime



# --- 日志记录配置 ---

# --- 暂时注释掉这段代码，让错误显示在 GitHub 控制台 ---
# log_file_path = 'scraper_log.txt'
# sys.stdout = open(log_file_path, 'a', encoding='utf-8')
# sys.stderr = open(log_file_path, 'a', encoding='utf-8')

print(f"\n--- Script started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

# --- 日志记录配置结束 ---



import sqlite3

import datetime

import json

from playwright.sync_api import sync_playwright



# ==============================================================================

# ---【配置区】---

# ==============================================================================



TARGET_URL = "https://tftb.sczwfw.gov.cn:8085/hos-server/pub/jmas/jmasbucket/jmopen_files/unzip/6e5032129863494a94bb2e2e7a2e9748/sltqszdsksssqxxpc/index.html#/"

DB_FILE = "reservoirs.db"

RESERVOIR_NAMES = ["二滩", "锦屏一级", "官地"]



# ==============================================================================

# ---【代码主体，无需修改】---

# ==============================================================================



def init_db():

    """初始化数据库"""

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute('''

        CREATE TABLE IF NOT EXISTS reservoir_data (

            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, record_time DATETIME NOT NULL,

            water_level REAL, inflow REAL, outflow REAL, capacity_level REAL);

    ''')

    conn.commit()

    conn.close()

    print("数据库初始化完成。")



def fetch_and_store_data():
    print("🚀 启动自动化浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print(f"🔗 正在访问: {TARGET_URL}")
            # 改为 networkidle，确保网络请求基本加载完
            page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)

            # 增加显式等待，防止页面空白
            page.wait_for_selector('input[placeholder="站名"]', timeout=30000)
            
            all_data = []
            for name in RESERVOIR_NAMES:
                print(f"正在查询水库: {name}...")
                input_box = page.locator('input[placeholder="站名"]')
                input_box.fill("") 
                input_box.fill(name)
                
                # 关键：填完名字等一秒，让前端响应
                page.wait_for_timeout(1500) 

                # 捕获响应
                try:
                    with page.expect_response("**/gateway.do", timeout=20000) as response_info:
                        page.locator("button.blue_button:has-text('搜索')").click()
                    
                    response = response_info.value
                    if response.ok:
                        # 打印原始响应的前100个字符用于调试
                        raw_text = response.text()
                        print(f"✅ 收到响应，长度: {len(raw_text)}")
                        
                        # 执行你之前的双重解包逻辑...
                        # (此处确保你的 json.loads 逻辑没有因为异常而跳过)
                        # ...
                except Exception as e:
                    print(f"❌ 查询 {name} 超时或失败: {e}")

            # 存储逻辑
            if all_data:
                save_to_sqlite(all_data) # 确保这个函数被调用了
            else:
                print("⚠️ 警告：all_data 列表为空，没有数据可存！")

        finally:
            browser.close()

if __name__ == "__main__":

    init_db()

    fetch_and_store_data() 




