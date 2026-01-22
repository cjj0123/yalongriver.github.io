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
    """使用Playwright自动化浏览器获取数据"""
    print("正在启动自动化浏览器...")
    with sync_playwright() as p:
        browser = None
        try:
            # --- 注意：下面这一行必须比 try 缩进 4 个空格 ---
            browser = p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = browser.new_page()
            # ... 后续代码也要保持同样的缩进层级 ...
            
        except Exception as e:
            print(f"自动化浏览器在执行过程中发生严重错误: {e}")
        finally:
            if browser and browser.is_connected():
                browser.close()
                print("浏览器已关闭。")

if __name__ == "__main__":

    init_db()

    fetch_and_store_data() 



