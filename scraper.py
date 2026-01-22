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
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        
        try:
            print(f"🔗 正在尝试访问: {TARGET_URL}")
            # 使用 domcontentloaded 策略提高海外访问成功率
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"⚠️ 页面加载超时或有异常，但我们将尝试继续定位元素: {e}")

        # --- 重要：抓取逻辑应该与上面的 try 平级，而不是缩进在 except 里面 ---
        all_data = []
        try:
            # 等待关键元素出现
            print("⏳ 等待页面输入框加载...")
            page.wait_for_selector('input[placeholder="站名"]', timeout=30000)
            
            for name in RESERVOIR_NAMES:
                print(f"🔍 正在查询水库: {name}...")
                input_box = page.locator('input[placeholder="站名"]')
                input_box.fill("") 
                input_box.fill(name)
                page.wait_for_timeout(1500) 

                try:
                    with page.expect_response("**/gateway.do", timeout=20000) as response_info:
                        page.locator("button.blue_button:has-text('搜索')").click()
                    
                    response = response_info.value
                    if response.ok:
                        raw_text = response.text()
                        outer_data = json.loads(raw_text)
                        
                        # --- 这里嵌入你之前的双重解包逻辑 ---
                        if outer_data.get('data') and isinstance(outer_data['data'], str):
                            inner_data = json.loads(outer_data['data'])
                            res_list = inner_data.get('result', {}).get('data', {}).get('list', [])
                            for item in res_list:
                                if item.get('zhanming') == name:
                                    all_data.append(item)
                                    print(f"✅ 成功解析到 {name} 的数据")
                                    break
                except Exception as e:
                    print(f"❌ 查询 {name} 失败: {e}")

            # 存储逻辑
            if all_data:
                save_to_sqlite(all_data) 
            else:
                print("⚠️ 警告：本次运行未抓取到任何有效数据。")

        except Exception as e:
            print(f"💥 脚本运行过程中发生严重错误: {e}")
        finally:
            browser.close()
            print("浏览器已关闭。")

def save_to_sqlite(data_list):
    """将数据存入数据库的辅助函数 (确保你代码中有这个函数)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    for res in data_list:
        # 这里使用你之前的字段映射逻辑
        cursor.execute('''
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (res.get("zhanming"), now, res.get("ksw"), res.get("rkll"), res.get("ckll"), float(res.get("xsl",0))/10000))
    conn.commit()
    conn.close()
    print(f"💾 成功写入 {len(data_list)} 条数据。")

import subprocess

def git_push_data():
    """本地运行完后自动提交到 GitHub"""
    try:
        print("正在同步数据到 GitHub...")
        subprocess.run(["git", "add", "reservoirs.db"], check=True)
        subprocess.run(["git", "commit", "-m", f"Manual Update: {datetime.datetime.now()}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🚀 数据已成功同步到 GitHub Pages！")
    except Exception as e:
        print(f"❌ 同步失败: {e}")

if __name__ == "__main__":
    init_db()
    fetch_and_store_data()
    git_push_data() # 执行完抓取后自动推送