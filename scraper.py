import sys
import datetime
import sqlite3
import json
import subprocess
from playwright.sync_api import sync_playwright

# --- 配置区 ---
TARGET_URL = "https://tftb.sczwfw.gov.cn:8085/hos-server/pub/jmas/jmasbucket/jmopen_files/unzip/6e5032129863494a94bb2e2e7a2e9748/sltqszdsksssqxxpc/index.html#/"
DB_FILE = "reservoirs.db"
RESERVOIR_NAMES = ["二滩", "锦屏一级", "官地"]

def init_db():
    """初始化数据库，增加 percentage 字段以适配前端图表"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 确保表结构包含所有需要的字段
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservoir_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL, 
            record_time DATETIME NOT NULL,
            water_level REAL, 
            inflow REAL, 
            outflow REAL, 
            capacity_level REAL,
            percentage REAL
        );
    ''')
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成。")

def safe_float(value, default=0.0):
    """安全转换浮点数，处理字符串、空值和短横线"""
    if value is None or value == "" or value == "-":
        return default
    try:
        return float(value)
    except ValueError:
        return default

def fetch_and_store_data():
    print("🚀 启动自动化浏览器...")
    with sync_playwright() as p:
        # 修正了之前代码中的缩进和 browser/context 初始化逻辑
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print(f"🔗 正在访问页面...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            all_data = []
            # 等待搜索框
            page.wait_for_selector('input[placeholder="站名"]', timeout=30000)
            
            for name in RESERVOIR_NAMES:
                print(f"🔍 正在查询: {name}...")
                input_box = page.locator('input[placeholder="站名"]')
                input_box.fill("") 
                input_box.fill(name)
                page.wait_for_timeout(1000) 

                try:
                    # 捕获接口响应
                    with page.expect_response("**/gateway.do", timeout=20000) as response_info:
                        page.locator("button.blue_button:has-text('搜索')").click()
                    
                    response = response_info.value
                    if response.ok:
                        outer_data = response.json()
                        # 双重解包逻辑
                        if 'data' in outer_data and isinstance(outer_data['data'], str):
                            inner_data = json.loads(outer_data['data'])
                            res_list = inner_data.get('result', {}).get('data', {}).get('list', [])
                            
                            for item in res_list:
                                if item.get('zhanming') == name:
                                    # 打印原始数据，方便你在 GitHub Action 日志里调试
                                    print(f"📊 {name} 原始数据样例: {item}")
                                    all_data.append(item)
                                    break
                except Exception as e:
                    print(f"❌ 查询 {name} 响应超时或解析失败: {e}")

            if all_data:
                save_to_sqlite(all_data) 
            else:
                print("⚠️ 警告：未抓取到任何有效数据。")

        except Exception as e:
            print(f"💥 严重错误: {e}")
        finally:
            browser.close()

def save_to_sqlite(data_list):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 使用抓取时的统一时间戳
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for res in data_list:
        # 这里的映射需要根据你打印出的原始数据调整
        # zhanming: 站名, ksw: 库水位, rkll: 入库流量, ckll: 出库流量, xsl: 蓄水量
        # 注意：如果 xsl 是蓄水量，通常需要一个最大容量才能算出百分比(percentage)
        # 这里假设 xsl 本身就是蓄水数据
        
        val_name = res.get("zhanming")
        val_water_level = safe_float(res.get("ksw"))
        val_inflow = safe_float(res.get("rkll"))
        val_outflow = safe_float(res.get("ckll"))
        # 核心修改：xsl / 100 转换为亿立方米
        raw_xsl = safe_float(res.get("xsl"))
        val_capacity = raw_xsl / 100.0  

        cursor.execute('''
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (val_name, now, val_water_level, val_inflow, val_outflow, val_capacity))
        
    conn.commit()
    conn.close()
    print(f"💾 成功写入 {len(data_list)} 条记录到数据库。")

def git_push_data():
    try:
        print("🔄 同步到 GitHub...")
        subprocess.run(["git", "config", "user.name", "Automated Scraper"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "add", "reservoirs.db"], check=True)
        # 如果没有变化，commit 会报错，所以用 check=False
        subprocess.run(["git", "commit", "-m", f"Data update: {datetime.datetime.now()}"], check=False)
        subprocess.run(["git", "push"], check=True)
        print("🚀 数据同步完成！")
    except Exception as e:
        print(f"⚠️ Git 操作提示: {e}")

if __name__ == "__main__":
    init_db()
    fetch_and_store_data()
    git_push_data()